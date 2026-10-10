#!/usr/bin/env python3
"""Build new gap36 stimuli and run only host/Spike prechecks; never launch RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
OLD = ROOT / "verification/out/gap35-vector-checked-preflight-20261004-03"
PIN_PLAN = ROOT / "verification/out/repaired-aligned-600-20260930-01/plan.json"
CARRY = "vgap36_carry_illegal"
WORDS = [0x42848557, 0x40848057, 0x4A848557, 0x48848057]
PREFIX = "ara_tb.dut.i_ara_soc.i_system.i_ara."


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def pins(paths):
    return {str(p): sha(p) for p in sorted(set(map(Path, paths)))}


def deps(path):
    text = path.read_text().replace("\\\n", " ")
    return {Path(p).resolve(strict=True) for p in shlex.split(text.split(":", 1)[1])}


def validate_log(name, log, checks, spike=False):
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|ERROR:|Fatal:)", log),
            "failure in precheck log")
    if spike:
        expected = "gap35 checks=555 failures=0"
        marker = "PASSED: " + str(ROOT / "apps/gap36-carry-illegal" / (name + ".c")) + "!"
    else:
        expected = marker = f"PASSED: {name} checks={checks} errors=0"
    require(log.splitlines().count(expected) == 1, "wrong/duplicate check total")
    require(log.splitlines().count(marker) == 1 and
            sum(line.startswith("PASSED:") for line in log.splitlines()) == 1,
            "wrong/duplicate PASS marker")


def source_audit():
    old_carry = (ROOT / "apps/riscv-tests/isa/rv64uv/vgap35_carry_illegal.c").read_text()
    new_carry = (ROOT / "apps/gap36-carry-illegal/vgap36_carry_illegal.c").read_text()
    preserved = new_carry.split("\nstatic volatile unsigned gap36_hook_calls;")[0].strip()
    expected = old_carry.replace('#include "vgap35_common.h"',
        '#include "../riscv-tests/isa/rv64uv/vgap35_common.h"').replace(
        "int main(void) {", "static int __attribute__((noinline)) gap36_carry_checks(void) {")
    require(preserved == expected.strip(), "carry body/expectations changed")
    old_akv = (ROOT / "apps/akv_gap35_descriptor/main.c").read_text()
    new_akv = (ROOT / "apps/gap36-akv-descriptor/descriptor.h").read_text()
    mutations = lambda s: s[s.index("    switch (test) {"):s.index("      default:")]
    require(mutations(old_akv) == mutations(new_akv), "AKV mutations changed")
    covered = []
    groups = []
    for i in range(6):
        first, count = 4 * i, 3 if i == 5 else 4
        source = ROOT / f"apps/gap36-akv-descriptor-{i}/main.c"
        require(f'gap36_descriptor_group({first}, {count}, "akv_gap36_descriptor_{i}")'
                in source.read_text(), "unexpected shard interval")
        covered.extend(range(first, first + count))
        groups.append({"name": f"akv_gap36_descriptor_{i}",
                       "original_illegal_indices": list(range(first, first + count)),
                       "dut_checks": count * 260 + 771, "host_checks": count * 257 + 772})
    require(covered == list(range(23)), "missing/duplicate original AKV mutation")
    return {"status": "PASS", "carry_original_body_and_expectations_unchanged": True,
            "carry_dut_and_spike_checks": 555, "carry_formula": "4*10 + 4*128 + 3",
            "akv_original_mutations_exact_once": covered, "groups": groups,
            "akv_shared_helpers": "Unmodified gap35 AKV and trap helpers: all 256 halfwords,"
            " trap count, cause=2, exact fault PC, tval=0 or opcode, valid row payload and guards.",
            "akv_error_scope": "Preserves architectural cause checks and ABI validity oracle;"
            " internal RTL validation_error enum is not architecturally read by the original test.",
            "akv_dut_formula": "illegal_count*(4+256) + 3*(1+256)",
            "akv_host_formula": "illegal_count*(1+256) + 258+258+256"}


def symbols(metadata):
    return {row["Symbol"]["Name"]["Name"]: row["Symbol"] for row in metadata["Symbols"]}


def code_bytes(metadata, blob, address, length):
    for entry in metadata["Sections"]:
        s = entry["Section"]
        if s["Flags"]["Value"] & 4 and s["Address"] <= address and \
                address + length <= s["Address"] + s["Size"]:
            off = s["Offset"] + address - s["Address"]
            return blob[off:off + length]
    raise ValueError("code address outside executable sections")


def carry_elf_audit(metadata, blob, dut):
    syms = symbols(metadata)
    function = syms["gap36_carry_checks"]
    body = code_bytes(metadata, blob, function["Value"], function["Size"])
    sites = []
    for word in WORDS:
        positions = [p for p in range(0, len(body) - 3, 2)
                     if int.from_bytes(body[p:p + 4], "little") == word]
        require(len(positions) == 1, "carry opcode missing/duplicated")
        sites.append(function["Value"] + positions[0])
    if dut:
        # Resolve the unmodified CRT's AUIPC/ADDI t0 followed by JALR t0.
        start = syms["_start"]["Value"]
        reset = code_bytes(metadata, blob, start, syms["trap_vector"]["Value"] - start)
        mret = reset.find(bytes.fromhex("73002030"))
        require(mret >= 0, "missing CRT MRET")
        matches = []
        for pos in range(0, mret - 7, 2):
            a = int.from_bytes(reset[pos:pos + 4], "little")
            b = int.from_bytes(reset[pos + 4:pos + 8], "little")
            if a & 0xfff != 0x297 or b & 0xfffff != 0x28293:
                continue
            high = a & 0xfffff000
            if high & 0x80000000:
                high -= 1 << 32
            low = b >> 20
            if low & 0x800:
                low -= 4096
            if start + pos + high + low == syms["rvtest_init"]["Value"]:
                require(bytes.fromhex("8292") in reset[pos + 8:mret],
                        "hook address not called before MRET")
                matches.append(start + pos)
        require(len(matches) == 1, "CRT does not bind rvtest_init once")
    else:
        # TLS NOBITS is a template, not ordinary storage below _end.
        end = syms["_end"]["Value"]
        tls_start = syms["_tdata_begin"]["Value"]
        tls_end = syms["_tbss_end"]["Value"]
        require(tls_end - tls_start >= 68, "HTIF putchar TLS omitted from initialization")
        for entry in metadata["Sections"]:
            sec = entry["Section"]
            if sec["Flags"]["Value"] & 2 and sec["Size"]:
                if sec["Flags"]["Value"] & 0x400:
                    require(tls_start <= sec["Address"] and
                            sec["Address"] + sec["Size"] <= tls_end, "uninitialized HTIF TLS")
                else:
                    require(sec["Address"] + sec["Size"] <= end,
                            "orphan non-TLS section after HTIF _end")
    main = syms["main"]
    main_bytes = code_bytes(metadata, blob, main["Value"], main["Size"])
    for pos in range(0, len(main_bytes) - 3, 2):
        word = int.from_bytes(main_bytes[pos:pos + 4], "little")
        require(not (word & 0x7f == 0x73 and word >> 20 == 0x305),
                "main still accesses mtvec")
    return {"status": "PASS", "illegal_sites": [hex(p) for p in sites],
            "illegal_words": [hex(w) for w in WORDS], "main_has_no_mtvec_access": True,
            "crt_calls_hook_before_mret": dut,
            "symbols": {n: hex(syms[n]["Value"]) for n in
                        ("rvtest_init", "gap36_carry_checks", "g35_trap", "main")}}


def trace_audit(trace, proof):
    commits = [(int(m[1]), int(m[2], 16), int(m[3], 16)) for m in re.finditer(
        r"(?m)^core\s+\d+:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)", trace)]
    require(commits, "no Spike privilege-bearing commit log")
    modes = {}
    for name, pc in proof["symbols"].items():
        values = [mode for mode, addr, _ in commits if addr == int(pc, 16)]
        require(values == ([3] * 4 if name == "g35_trap" else [0] if name == "main" else [3]),
                f"wrong privilege/call count at {name}: {values}")
        modes[name] = values
    faults = [(m[1], int(m[2], 16)) for m in re.finditer(
        r"exception ([^,]+), epc 0x([0-9a-f]+)", trace)]
    require(faults == [("trap_illegal_instruction", int(pc, 16))
                       for pc in proof["illegal_sites"]], "unexpected trap/PC sequence")
    require(all(mode == 3 for mode, _, word in commits
                if word & 0x7f == 0x73 and word >> 20 == 0x305),
            "machine vector CSR executed outside M mode")
    return {"status": "PASS", "symbol_entry_privileges": modes,
            "trap_count": len(faults), "trap_pcs": [hex(pc) for _, pc in faults],
            "main_is_user_mode": True, "hook_and_test_are_machine_mode": True,
            "unexpected_traps": 0, "retired_log_entries": len(commits)}


class Build:
    def __init__(self, out):
        self.out = out
        self.commands = []
        self.llvm = (ROOT / "install/riscv-llvm").resolve()
        self.cc = self.llvm / "bin/clang"
        self.common = ROOT / "apps/common"
        self.flags = ["--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
                      "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu11", "-fno-vectorize",
                      "-fno-slp-vectorize", "-fno-fast-math", "-ffp-contract=off",
                      "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
                      "-ffunction-sections", "-fdata-sections", "-DNR_LANES=4", "-DVLEN=1024"]
        self.inc = [f"-I{ROOT / p}" for p in ("apps/common", "apps/include",
            "apps/riscv-tests/isa/macros/scalar", "apps/riscv-tests/isa/macros/vector")]
        self.common_objects = []
        self.common_sources = {self.common / "link.ld", SCRIPT}

    def run(self, argv, label, timeout=120, split=False):
        argv = list(map(str, argv))
        self.commands.append({"command": argv, "cwd": str(ROOT), "timeout_s": timeout})
        save(self.out / "commands.json", self.commands)
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
        (self.out / (label + ".log")).write_bytes(
            result.stdout if split else result.stdout + result.stderr)
        if split:
            (self.out / (label + ".trace.log")).write_bytes(result.stderr)
        require(result.returncode == 0, f"{label} failed: {self.out / (label + '.log')}")
        return result

    def compile(self, source, label, extra=(), host=False):
        obj = self.out / (label + ".o")
        dep = self.out / (label + ".d")
        compiler = ["cc", "-O2", "-std=gnu11", "-fno-fast-math", "-ffp-contract=off",
                    "-fno-tree-vectorize", "-DGAP35_HOST", f"-I{self.common}"] if host else [
                        self.cc, *self.flags, *self.inc]
        self.run([*compiler, *extra, "-MD", "-MF", dep, "-c", source, "-o", obj], label + ".compile")
        return obj, deps(dep)

    def runtime(self):
        for n in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"):
            obj, sources = self.compile(self.common / n, "dut-" + n)
            self.common_objects.append(obj)
            self.common_sources.update(sources)

    def link_dut(self, source, name):
        obj, sources = self.compile(source, name, ["-Wall", "-Wextra", "-Wno-unused-function"])
        elf = self.out / (name + ".elf")
        self.run([self.cc, *self.flags, "-fuse-ld=lld", "-static", "-nostartfiles",
                  "-Wl,--gc-sections", f"-Wl,-Map={self.out / (name + '.map')}",
                  f"-T{self.common / 'link.ld'}", obj, *self.common_objects, "-lm",
                  f"-L{self.llvm / 'lib/generic'}", "-lclang_rt.builtins-riscv64", "-o", elf],
                 name + ".link")
        self.run([ROOT / "verification/tools/soc-venv/bin/python",
                  ROOT / "verification/coverage/check_elf_fit.py", "--elf", elf,
                  "--ram-bytes", "0x200000", "--output", self.out / (name + ".elf-fit.json")],
                 name + ".elf-fit")
        return elf, sources | self.common_sources

    def metadata(self, elf, name):
        self.run([self.llvm / "bin/llvm-objdump", "-d", elf], name + ".disassembly")
        result = self.run([self.llvm / "bin/llvm-readobj", "--elf-output-style=JSON",
                           "--sections", "--symbols", "--program-headers", elf], name + ".metadata")
        return json.loads(result.stdout)[0]


def latest_baseline(image):
    candidates = []
    for path in (ROOT / "verification/out").glob("*/collection.json"):
        value = read(path)
        if value.get("status") in ("PASS", "COMPLETE_WITH_FAILURES") and value.get("image") == image \
                and (path.parent / "combined-bits.json").is_file() \
                and (path.parent / "all-passed-outcomes.json").is_file():
            candidates.append((value["passed"], path.stat().st_mtime_ns, path.parent))
    require(candidates, "no complete same-image baseline")
    _, _, base = max(candidates)
    rows = read(base / "all-passed-outcomes.json")
    bits = read(base / "combined-bits.json")
    inputs = (base / "combined-dve/inputs.txt").read_text().splitlines()
    require(len(rows) == read(base / "collection.json")["passed"] and
            bits["tests"] == inputs[1:] == [r["vdb"] for r in rows], "baseline membership differs")
    require(all(r["status"] == "PASS" and r["passed_only"] and r["vdb_valid"] for r in rows),
            "baseline contains non-PASS cases")
    return base, len(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    require(out.parent == ROOT / "verification/out" and out.name.startswith("gap36-")
            and not out.exists(), "a NEW verification/out/gap36-* output is required")
    plan = read(OLD / "plan.json")
    frozen = {}
    for case in plan["cases"]:
        if case["name"] in ("akv_gap35_descriptor", "vgap35_carry_illegal"):
            frozen.update(case["source_files"])
    for path, digest in frozen.items():
        require(sha(path) == digest, "old frozen source/ELF drift: " + path)
    oracle = next(c for c in read(PIN_PLAN)["cases"] if c.get("spike"))
    spike = Path(oracle["spike"])
    require(sha(spike) == oracle["spike_sha256"], "restart-capable Spike pin mismatch")
    audit = source_audit()
    out.mkdir()
    save(out / "source-audit.json", audit)
    save(out / "old-input-pins.json", frozen)
    b = Build(out)
    b.runtime()
    cases = []
    artifacts = []
    carry_source = ROOT / "apps/gap36-carry-illegal" / (CARRY + ".c")
    elf, sources = b.link_dut(carry_source, CARRY)
    proof = carry_elf_audit(b.metadata(elf, CARRY), elf.read_bytes(), True)
    runtime = ROOT / "apps/riscv-tests/benchmarks/common"
    extra = ["-D__SPIKE__=1", "-DPREALLOCATE=1", f"-I{runtime}",
             f"-I{ROOT / 'apps/riscv-tests/env'}",
             "-fno-function-sections", "-fno-data-sections"]
    objects = []
    for src, label in [(runtime / "crt.S", "spike-crt"),
                       (runtime / "syscalls.c", "spike-syscalls"),
                       (carry_source.parent / "spike_privilege.S", "spike-privilege"),
                       (carry_source, "spike-carry")]:
        obj, dependencies = b.compile(src, label, extra)
        objects.append(obj)
        sources.update(dependencies)
    sources.add(runtime / "test.ld")
    spike_elf = out / (CARRY + ".spike")
    b.run([b.cc, *b.flags, "-fuse-ld=lld", "-static", "-nostdlib",
           "-Wl,--wrap=main", f"-T{runtime / 'test.ld'}", *objects, "-o", spike_elf],
          CARRY + ".spike-link")
    spike_proof = carry_elf_audit(b.metadata(spike_elf, CARRY + ".spike"), spike_elf.read_bytes(), False)
    command = [spike, "--isa=rv64gcv_zfh_zvl1024b", "-l", "--log-commits", spike_elf]
    started = time.monotonic()
    result = b.run(command, CARRY + ".spike", timeout=30, split=True)
    seconds = time.monotonic() - started
    validate_log(CARRY, result.stdout.decode(), 555, True)
    trace = trace_audit(result.stderr.decode(), spike_proof)
    privilege = {
        "status": "PASS", "dut_static_audit": proof, "spike_static_audit": spike_proof,
        "spike_dynamic_audit": trace,
        "old_mismatch": "Old Spike benchmark CRT calls main in M mode; DUT crt0 mret enters U mode."
        " Old Spike PASS did not validate the DUT's privileged mtvec setup inside main.",
        "corrected_contract": "Both paths call the identical rvtest_init/test body in M mode once;"
        " only the result gate runs in U-mode main. Spike uses --wrap=main with explicit MPP=U,"
        " PMP allow-all, mepc and mret, and its commit trace must prove the privilege sequence.",
        "unchanged_expectations": "Exact original 555 checks, all four trap mtvals/PCs and vstart,"
        " vl/vtype/fcsr/vcsr values, and every byte of v0/v8/v9/v10.",
        "limitation": "Spike and DUT still have separate I/O/link runtimes and ELFs. This checks"
        " the privilege contract, not DUT execution or complete runtime equivalence.",
        "legacy_counter_label": "gap35 checks=555 is retained by the unchanged common header"
        " and rvv-spike-v1 log schema; the testcase/ELF/PASS path is vgap36_carry_illegal."
    }
    save(out / "privilege-audit.json", privilege)
    row = {"test": "rvv:" + CARRY, "status": "PASS", "returncode": 0, "seconds": seconds,
           "command": list(map(str, command)), "binary": str(elf), "binary_sha256": sha(elf),
           "spike_tool_sha256": sha(spike), "spike_binary": str(spike_elf),
           "spike_sha256": sha(spike_elf), "log": str(out / (CARRY + ".spike.log")),
           "source_hashes": pins(sources), "checks": 555, "vcs_launched": False,
           "privilege_audit": str(out / "privilege-audit.json"),
           "trace_log": str(out / (CARRY + ".spike.trace.log"))}
    row["log_sha256"] = sha(row["log"])
    row["trace_sha256"] = sha(row["trace_log"])
    save(out / "spike_results.json", [row])
    cases.append({"name": "rvv:" + CARRY, "binary": str(elf), "sources": sorted(map(str, sources)),
                  "evidence": [str(out / n) for n in ("spike_results.json", CARRY + ".spike.log",
                      CARRY + ".spike.trace.log", CARRY + ".spike", "privilege-audit.json",
                      "source-audit.json", CARRY + ".disassembly.log", CARRY + ".elf-fit.json")],
                  "source_audit": privilege["unchanged_expectations"] + " " + privilege["corrected_contract"],
                  "targets": [PREFIX + "i_dispatcher"],
                  "rationale": "Corrected privileged startup for the four original VADC/VSBC illegal encodings;"
                  " no weaker expected result or trap/VRF guard. No VCS PASS claimed.",
                  "timeout_s": 300, "precheck": {"format": "rvv-spike-v1",
                      "record": str(out / "spike_results.json"), "log": row["log"]}})
    artifacts.append(row)
    print(CARRY, "Spike PASS, checks=555, M-hook/U-main trace PASS", flush=True)
    reference = ROOT / "software/akv/src/akv_v2_reference.c"
    host_ref, ref_deps = b.compile(reference, "host-akv-reference", host=True)
    for group in audit["groups"]:
        name = group["name"]
        i = int(name[-1])
        source = ROOT / f"apps/gap36-akv-descriptor-{i}/main.c"
        host_obj, host_deps = b.compile(source, name + ".host", host=True)
        host = out / (name + ".host")
        b.run(["cc", host_obj, host_ref, "-lm", "-o", host], name + ".host-link")
        result = b.run([host], name + ".reference", timeout=30)
        validate_log(name, result.stdout.decode(), group["host_checks"])
        elf, sources = b.link_dut(source, name)
        b.metadata(elf, name)
        sources.update(host_deps | ref_deps)
        record = {"name": name, "binary": str(elf), "binary_sha256": sha(elf),
                  "sources": sorted(map(str, sources)), "source_hashes": pins(sources),
                  "host_result": result.stdout.decode().strip(), "host_reference": str(reference),
                  "host_log": str(out / (name + ".reference.log")), "host_binary": str(host),
                  "host_binary_sha256": sha(host),
                  "elf_fit": str(out / (name + ".elf-fit.json")),
                  "disassembly": str(out / (name + ".disassembly.log")),
                  "custom_instruction_execution_prechecked": False, "vcs_launched": False,
                  "checked_scope": "host-reference-only", **group}
        record["host_log_sha256"] = sha(record["host_log"])
        save(out / (name + ".precheck.json"), record)
        artifacts.append(record)
        cases.append({"name": "app:" + name, "binary": str(elf),
                      "sources": record["sources"],
                      "evidence": [str(out / n) for n in (name + ".precheck.json",
                          name + ".reference.log", name + ".elf-fit.json",
                          name + ".disassembly.log", "source-audit.json")],
                      "source_audit": f"Original invalid cases {group['original_illegal_indices']}; "
                      + audit["akv_shared_helpers"] + f" DUT checks={group['dut_checks']};"
                      f" host checks={group['host_checks']}, host-reference-only.",
                      "targets": [PREFIX + "i_vlsu.i_akv_engine"],
                      "rationale": "Bounded split of the original descriptor campaign; every shard ends"
                      " with the original valid V2 fill, V row2 load and release. Budget derived from"
                      " saved ~16408.5 cycles/fill and ~292.946 cycles/wall-second; no DUT run yet.",
                      "timeout_s": 600, "precheck": {"format": "accel-host-v1",
                          "record": str(out / (name + ".precheck.json"))}})
        print(name, f"host PASS checks={group['host_checks']}; DUT expects {group['dut_checks']}", flush=True)
    baseline, passed = latest_baseline(plan["image"])
    selection = {"baseline": str(baseline), "baseline_bits": str(baseline / "combined-bits.json"),
                 "cases": cases}
    save(out / "selection-draft.json", selection)
    # Only native per-case read-only admission. Do not call prepare/validate/launch.
    sys.path.insert(0, str(ROOT / "verification/coverage"))
    import coverage_evidence
    evidence = coverage_evidence.Evidence()
    checked = [coverage_evidence.precheck(c, evidence) for c in cases]
    save(out / "checked-prechecks.json", {"status": "PASS", "cases": checked,
         "checked_files": evidence.files, "vcs_launched": False,
         "full_baseline_admission_run": False, "selection_sha256": sha(out / "selection-draft.json")})
    negative = []
    good = (out / (CARRY + ".spike.log")).read_text()
    for label, bad in (("missing-check", good.replace("555", "554")),
                       ("duplicate-summary", good + good), ("failure", good + "\nFAIL harness\n")):
        try:
            validate_log(CARRY, bad, 555, True)
        except ValueError:
            negative.append(label)
        else:
            raise ValueError("accepted bad log: " + label)
    save(out / "negative-log-audit.json", {"status": "PASS", "rejected": negative,
         "scope": "In-memory log mutations only; no altered ELF or extra model run."})
    for path, digest in frozen.items():
        require(sha(path) == digest, "old input changed during build: " + path)
    for item in artifacts:
        for path, digest in item["source_hashes"].items():
            require(sha(path) == digest, "compile source changed during build: " + path)
    tools = [spike, b.cc.resolve(), (b.llvm / "bin/ld.lld").resolve(),
             (b.llvm / "bin/llvm-objdump").resolve(), (b.llvm / "bin/llvm-readobj").resolve(),
             Path(shutil.which("cc")).resolve(), Path(sys.executable).resolve(),
             ROOT / "verification/coverage/check_elf_fit.py",
             ROOT / "verification/coverage/coverage_evidence.py"]
    inputs = {**frozen, **pins(tools + [PIN_PLAN, OLD / "plan.json",
        baseline / "collection.json", baseline / "combined-bits.json",
        baseline / "all-passed-outcomes.json", baseline / "combined-dve/inputs.txt"])}
    for item in artifacts:
        inputs.update(item["source_hashes"])
    save(out / "input-hashes.json", inputs)
    save(out / "build-results.json", {"status": "PRECHECK_PASS_RTL_NOT_RUN", "cases": artifacts,
         "vcs_launched": False, "old_frozen_inputs_unchanged": True})
    save(out / "handoff.json", {"status": "DRAFT_NOT_AUTHORIZATION_TO_LAUNCH",
         "baseline": str(baseline), "baseline_passed": passed, "baseline_policy":
         "Latest complete same-image collection at build handoff; parent must rebase/check at freeze.",
         "cases": len(cases), "checked_formats": {"rvv-spike-v1": 1, "accel-host-v1": 6},
         "carry_checks": 555, "akv_groups": audit["groups"],
         "akv_budget": {"per_case_s": 600, "measured_reference_cycles_per_fill": 16408.5,
                       "measured_reference_cycles_per_wall_s": 292.9461340095364,
                       "five_fill_estimate_s": 280.063434040629,
                       "four_fill_estimate_s": 224.050747232503,
                       "note": "Plus startup, valid-payload/replay/release and finish overhead."
                       " 600 s is a draft ceiling, not measured shard duration or a PASS promise."},
         "qbs": "Not included; parent owns same-ELF QBS 600 s retry.",
         "vcs_launched": False, "rtl_modified": False, "old_files_modified": False})
    save(out / "artifact-hashes.json", pins(p for p in out.iterdir() if p.is_file()))
    print("Checked native prechecks: 7 PASS; baseline", passed, baseline, flush=True)
    print("No VCS, DVE, URG, Verilator or ZCC launched. Draft:", out / "selection-draft.json")


if __name__ == "__main__":
    main()
