#!/usr/bin/env python3
"""Compile and seal one QBS context case. Host checks only, never launch RTL."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import build_gap36_timeout_successors as common

ROOT, require, read, save, sha, pins = (common.ROOT, common.require, common.read,
                                      common.save, common.sha, common.pins)
SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "verification/coverage"))
import coverage_evidence as evidence
import gap45_qbs_context_admission as admission
import run_gap45_qbs_checked_extension as adapter
import test_gap45_qbs_context as tests

NAME = admission.NAME
BUILD = ROOT / "verification/out/repaired-aligned-build-20260930-01"
ANALYSIS = ROOT / "verification/out/gap40-custom-analysis-20261004-01"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    out = parser.parse_args().output.resolve()
    require(out.parent == ROOT / "verification/out" and out.name.startswith("gap45-") and not out.exists(),
            "new local verification/out/gap45-* directory required")
    out.mkdir()
    b = common.Build(out)
    protected = pins([ROOT / p for p in ("apps/qbs_gap35_common/test.h", "verification/qbs/qbs_ref.c",
        "verification/qbs/qbs_ref.h", "verification/tests/build_gap36_timeout_successors.py",
        "verification/coverage/run_checked_extension.py", "verification/coverage/coverage_evidence.py",
        "verification/coverage/run_targeted_extension.py", "verification/coverage/run_full_recollection_20260928.py",
        "verification/coverage/run_vcs_dve_batch.py", "verification/ara_verify/runner.py")])
    build_pins = read(BUILD / "build-source-pins.json")
    rtl_paths = [ROOT / p for p in ("hardware/src/vlsu/qbs/qbs_engine.sv",
        "hardware/src/vlsu/qbs/qbs_activation_context.sv", "hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv",
        "hardware/src/vlsu/vlsu.sv", "hardware/src/ara_dispatcher.sv", "hardware/include/qbs_pkg.sv",
        "config/default.mk")]
    rtl_pins = {str(p): build_pins[str(p)] for p in rtl_paths}
    for p, h in rtl_pins.items():
        require(sha(p) == h, "frozen RTL/config drift: " + p)
    baseline, count = common.latest_baseline(read(BUILD / "build-image.json"))
    bits = read(baseline / "combined-bits.json")
    targets = [p for p in read(ANALYSIS / "candidate-points.json") if p["plan"] == "QBS"]
    require(len(targets) == 8, "original Plan Q must have eight points")
    for p in targets:
        value = bits["metrics"][p["metric"]][p["scope"]]
        require(value["checksum"] == p["definition"]["checksum"] and value["width"] == p["definition"]["width"],
                "baseline target identity differs")
        p["hit_at_build"] = int(format(int(value["bits"], 16), f"0{value['width']}b")[p["raw_index"]])
        require(p["hit_at_build"] == 0, "context target already covered; parent must review selection")
    b.runtime()
    source = ROOT / "apps" / NAME / "main.c"
    reference = ROOT / "verification/qbs/qbs_ref.c"
    ref_obj, ref_deps = b.compile(reference, "host-qbs-reference", host=True)
    host_obj, host_deps = b.compile(source, NAME + ".host", host=True)
    host = out / (NAME + ".host")
    b.run(["cc", host_obj, ref_obj, "-lm", "-o", host], NAME + ".host-link")
    require("GAP45_NEGATIVE" not in os.environ, "unexpected host mutation environment")
    result = b.run([host], NAME + ".reference", timeout=30)
    admission.validate_log(result.stdout.decode(), host=True)
    print("Host reference PASS: 172 checks, eight operations", flush=True)
    host_negative = []
    for mutation in ("generation", "vrf", "source"):
        command = [str(host)]
        b.commands.append(dict(command=command, cwd=str(ROOT), timeout_s=30,
                               env_overrides=dict(GAP45_NEGATIVE=mutation), expected_returncode=1))
        save(out / "commands.json", b.commands)
        value = subprocess.run(command, cwd=ROOT, env=dict(os.environ, GAP45_NEGATIVE=mutation),
                               capture_output=True, timeout=30)
        log = out / ("negative-host-" + mutation + ".log")
        log.write_bytes(value.stdout + value.stderr)
        require(value.returncode == 1 and b"FAILED: qbs_gap45_context" in value.stdout,
                "host mutation escaped: " + mutation)
        host_negative.append(dict(mutation=mutation, returncode=value.returncode, log=str(log), sha256=sha(log)))
    elf, sources = b.link_dut(source, NAME)
    metadata = b.metadata(elf, NAME)
    save(out / "elf-metadata.json", metadata)
    elf_audit = admission.elf_audit(metadata, elf.read_bytes())
    save(out / "elf-audit.json", elf_audit)
    print("DUT ELF compile/fit/static audit PASS; no DUT execution", flush=True)
    scratch = out / "synthetic-checker-fixtures-NOT-DUT"
    scratch.mkdir()
    negative = tests.run(metadata, elf.read_bytes(), result.stdout.decode(), scratch, targets, elf)
    negative["host_mutations"] = host_negative
    save(out / "negative-tests.json", negative)
    sources.update(host_deps | ref_deps | {SCRIPT, Path(tests.__file__), admission.SCRIPT, adapter.SCRIPT})
    sources.update(Path(p) for p in protected)
    tools = [b.cc.resolve(), (b.llvm / "bin/ld.lld").resolve(),
        (b.llvm / "bin/llvm-objdump").resolve(), (b.llvm / "bin/llvm-readobj").resolve(),
        Path(shutil.which("cc")).resolve(), Path(sys.executable).resolve(),
        ROOT / "verification/coverage/check_elf_fit.py"]
    inputs = {**protected, **rtl_pins, **pins(tools + [BUILD / "build-source-pins.json",
        BUILD / "build-image.json", BUILD / "compile.command.json", ANALYSIS / "candidate-points.json",
        ANALYSIS / "validation.json", baseline / "combined-bits.json", baseline / "collection.json",
        baseline / "all-passed-outcomes.json", baseline / "combined-dve/inputs.txt"])}
    save(out / "input-hashes.json", inputs)
    record = dict(name=NAME, schema=admission.SCHEMA, binary=str(elf), binary_sha256=sha(elf),
        sources=sorted(map(str, sources)), source_hashes=pins(sources), host_reference=str(reference),
        host_result=result.stdout.decode().strip(), host_log=str(out / (NAME + ".reference.log")),
        host_binary=str(host), host_binary_sha256=sha(host), host_checks=172, dut_checks=198,
        custom_instruction_execution_prechecked=False, vcs_launched=False,
        metadata=str(out / "elf-metadata.json"), elf_audit=elf_audit, rtl_pins=rtl_pins, targets=targets,
        baseline=str(baseline), baseline_passed=count)
    save(out / (NAME + ".precheck.json"), record)
    audit = "Eight QBS V2 context commands; independent qbs_ref plus exact hand results 256/512. " \
        "Each command compares all 1024 words of v0-v31, 159 source/guard uint64 words, and destination guards. " \
        "DUT checks immediate fflags/vstart and trap count/cause/exact opcode PC/tval; host checks=172, DUT=198."
    item = dict(name="app:" + NAME, binary=str(elf), sources=record["sources"],
        evidence=[str(out / n) for n in (NAME + ".precheck.json", NAME + ".reference.log",
            NAME + ".elf-fit.json", NAME + ".disassembly.log", "elf-metadata.json", "elf-audit.json",
            "negative-tests.json", "input-hashes.json")],
        source_audit=audit, targets=sorted({p["scope"] for p in targets}), timeout_s=600,
        rationale="Original Plan Q: generation mismatch, preserved reuse, K mismatch, preserved release, "
        "invalid reuse, new-generation refill/release. Eight still-missing context error coordinates. "
        "Host-only precheck; runtime requires eight QBS_PERF identities and exact target hits.",
        precheck=dict(format="accel-host-v1", record=str(out / (NAME + ".precheck.json"))))
    save(out / "selection.json", dict(baseline=str(baseline), baseline_bits=str(baseline / "combined-bits.json"), cases=[item]))
    proof = evidence.Evidence()
    native = admission.NATIVE_PRECHECK(item, proof)
    save(out / "checked-precheck.json", dict(status="PASS", result=native, checked_files=proof.files,
        vcs_launched=False, full_baseline_admission_run=False))
    for path, digest in {**inputs, **record["source_hashes"]}.items():
        require(sha(path) == digest, "input changed during build: " + path)
    save(out / "build-results.json", dict(status="PRECHECK_PASS_RTL_NOT_RUN", case=NAME,
        baseline_passed=count, missing_targets=len(targets), host_checks=172, dut_checks_expected=198,
        host_mutations_rejected=len(host_negative), offline_mutations_rejected=len(negative["rejected"]),
        timeout_s=600, measured_runtime_s=None, vcs_launched=False, old_inputs_unchanged=True,
        adapter=str(adapter.SCRIPT), hook="install_hooks", checked_script_changed_by_hook=False))
    (out / "README.md").write_text(f"""# QBS Gap45 Context Handoff

Status: PRECHECK_PASS_RTL_NOT_RUN. One standard `selection.json` case:
`app:qbs_gap45_context`, hard simulator timeout 600 seconds. No simulation,
Spike, DVE, URG or Verilator was launched. No RTL, policy, frozen helper or old
outcome was edited. Full historical batch admission remains the parent's job.

## Parent Integration

Import `verification/coverage/run_gap45_qbs_checked_extension.py` and call
`install_hooks()` in every parent entry process (prepare/worker/directed/summary).
It chains precheck, worker, summarize and directed handlers and delegates other
cases. Installation is idempotent and does not set `checked.SCRIPT`; only the
standalone `main()` does. The parent runner must retain its own SCRIPT.

Keep this case object EXACTLY equal to `selection.json["cases"][0]`. Do not add
sources, evidence or annotations to the case. Bind draft/composer at batch level.
This case does not pin the parent composer. Runtime proof objects use string
dictionary keys and pass JSON roundtrip plus summarize replay tests.

The default worker does not enable QBS_PERF: `ara_verify/runner.py` constructs
TESTCASE/NO_FSDB/COMMIT_TRACE only. The local directed hook adds exactly one
`+QBS_PERF` only for this name and restores the monitored runner on exit. Original
command.json remains the helper's command; gap45-command.json records the local
injection and coverage.command.json records the actual simulator argv. Runtime
admission binds the latter and the original simulator log to the checked row.

## Eight Operations

All use opcode 0x00b5045b (M1/vd8), Q4_K/Q8_K, N1, context0, aligned mapped
buffers holding TWO valid blocks. K2 is legal metadata, not a short buffer.

| Step | Operation | Generation | K | Oracle |
| --- | --- | --- | --- | --- |
| 1 | FILL epoch A | 0x35 | 1 | success, 256 |
| 2 | REUSE | 0x36 | 1 | trap, generation error19 |
| 3 | REUSE | 0x35 | 1 | success, cached256 |
| 4 | REUSE | 0x35 | 2 | trap, metadata error20 |
| 5 | RELEASE | 0x35 | 1 | success, cached256 |
| 6 | REUSE | 0x35 | 1 | trap, invalid error18 |
| 7 | FILL epoch B | 0x36 | 1 | success, 512 |
| 8 | RELEASE | 0x36 | 1 | success, 512 |

External activation is poisoned to epoch B immediately after step1; correct
steps3/5 must not read it. Q4_K all quantized weights1 and FP scales1 dot Q8_K
ones gives 256 (0x43800000); twos gives512 (0x44000000). Independent unmodified
qbs_ref executes the same sequence and agrees with the hand oracle.

Each DUT step seeds and captures ALL v0-v31 (1024 words), not only v8-v15. Success
changes v8[0], zeroes v8[1..31], preserves the other 992 words. Fault preserves
all1024. Captured output is pre-poisoned separately to detect missing stores.
All 8192 sampled VRF words and 1272 uint64 source/guard words are compared.
`equal64` ORs EVERY XOR difference then checks once; reduced check count is
aggregation, not sampling or dropping comparisons. Per-step destination guards,
descriptor/weights/activation content and guards are checked. Faults check
count/cause2/exact opcode PC/tval0-or-opcode. fflags/vstart are both sampled before
any post-instruction vsetvli and required zero on each DUT step.

Host checks=172: 8*(status1+VRF1+outputguards16+sources3)+final4.
DUT checks=198: 8*(trapcount1+flags2+VRF1+outputguards16+sources3)+trapdetails9+final5.

## Coverage And Evidence Limits

Latest completed same-image baseline at build: {count} checked PASS cases,
`{baseline}`. All eight original targets remain zero. The record contains full
raw indexes, module/metric/point checksums, branchvectors and original source
coordinates. Runtime requires all eight same-checksum raw bits to be one:

| Scope suffix | Coordinate | Raw index |
| --- | --- | --- |
| i_qbs_engine.i_activation_context | Block6 | 7 |
| i_qbs_engine.i_activation_context | Block8 | 9 |
| i_qbs_engine.i_activation_context | Block10 | 11 |
| i_qbs_engine.i_activation_context | Branch0(0) | 4 |
| i_qbs_engine.i_activation_context | Branch0(1) | 3 |
| i_qbs_engine.i_activation_context | Branch0(2) | 2 |
| i_qbs_engine | Block185 | 186 |
| i_qbs_engine | Branch29(9) | 167 |

Native functional/protocol/trace admission remains in force. Additional runtime
proof requires eight unique ordered PERF sequences, exact M/N/VLEN/lanes/modes,
S,F,S,F,S,F,S,S and 19/20/18, per-command context counters, read bytes/ranges and
no fault commits. Static linked PC, exact fault-PC selfcheck and sole custom
site plus these terminal records suffice here; no dynamic PC inference is used.
The last RELEASE invalidation is directly observed only in the host model;
DUT invalidation is explicitly tested at step5->6, not with a ninth command.

Compilation/static ELF/host/reference and synthetic checker fixtures do not
prove DUT behavior, target hits or wall time. The expanded all-register oracle
was not benchmarked; 600s is a ceiling, not a measured duration. No timeout
escalation or waiver approval is implied. Preserve first-failure artifacts.

## Seals

`checked-precheck.json` stores the exact native result and checked file map.
`artifact-hashes.json` seals build artifacts, negative tests and inputs.
`seal.json` binds selection, native result and artifact manifest. The adapter
replays native admission and requires identical result AND identical file map.
`sealed-precheck-result.json` stores final adapter admission plus four exact-case
mutation rejections. `final-seal.json` binds this result and seal.json.
Synthetic fixtures are explicitly named NOT-DUT; none is a real run outcome.
""")
    save(out / "artifact-hashes.json", pins(p for p in out.rglob("*") if p.is_file()))
    save(out / "seal.json", pins(out / n for n in ("selection.json", "checked-precheck.json", "artifact-hashes.json")))
    adapter.install_hooks()
    proof = evidence.Evidence()
    checked = evidence.precheck(item, proof)
    sealed = tests.sealed_tests(item, out / "selection.json")
    save(out / "sealed-precheck-result.json", dict(status="PRECHECK_PASS_RTL_NOT_RUN", result=checked,
        checked_files=proof.files, sealed_negative_tests=sealed, vcs_launched=False,
        full_baseline_admission_run=False, selection_sha256=sha(out / "selection.json")))
    save(out / "final-seal.json", pins(out / n for n in ("seal.json", "sealed-precheck-result.json")))
    print("Sealed native + case adapter precheck PASS;", len(negative["rejected"]),
          "offline rejections, 3 host mutations, 4 exact-case mutations", flush=True)
    print("Selection:", out / "selection.json", "sha256=" + sha(out / "selection.json"))
    print("No VCS/DVE/URG/Verilator/Spike launched. Parent must run full checked batch admission.")


if __name__ == "__main__":
    main()
