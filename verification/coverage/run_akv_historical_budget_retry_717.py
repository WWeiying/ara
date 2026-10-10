"""Prepare two independent same-ELF/old-image budget retries; no admission."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import akv_historical_budget_oracle_717 as oracle
from audit_historical_nonpass_717 import Audit, OUT, ROOT, sha

IMAGE = OUT / "repaired-aligned-build-20260930-01/sim/simv"
IMAGE_SHA = "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"
CASES = {
    oracle.DESCRIPTOR: ("gap35-vector-checked-preflight-20261004-03", 300, 1800,
                        "f08781d48f8a29a5413850b54af4de7d4c31117bc588934acfd6d46b585df7c2"),
    oracle.SKEW: ("gap48-current-20261004-01", 600, 3000,
                  "bb333b09bee3df3280dff94abb0aedb257c8c7ae434396c7c5b604d470ab0051")}


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def bound(path, digest):
    oracle.require(sha(path) == digest, "Sealed input drift: " + str(path))
    return json.loads(Path(path).read_text())


def check_pins(pins):
    for path, digest in pins.items():
        oracle.require(sha(path) == digest, "Input drift: " + path)


def image_inventory(image):
    return {str(p): sha(p) for p in [image, *sorted(Path(str(image) + ".daidir").rglob("*.so"))]}


def command_for(original, output, name):
    oracle.require(original[0] == str(IMAGE) and original.count("+TESTCASE=" + name) == 1
                   and original.count("+NO_FSDB") == 1
                   and original.count("-cm") == original.count("-cm_dir") == original.count("-cm_name") == 1,
                   "Original exact simulator command differs")
    oracle.require(sum(s.startswith("+PRELOAD=") for s in original) == 1
                   and sum(s.startswith("+COMMIT_TRACE=") for s in original) == 1,
                   "Original ELF/trace command binding ambiguous")
    cmd = list(original)
    cmd = ["+PRELOAD=" + str(output / "input.elf") if s.startswith("+PRELOAD=") else
           "+COMMIT_TRACE=" + str(output / "commit_trace.csv") if s.startswith("+COMMIT_TRACE=") else s
           for s in cmd]
    cmd[cmd.index("-cm_dir") + 1] = str(output / "code.vdb")
    oracle.require(not any(s.startswith(("+VECTOR_TRACE=", "+COMMIT_TOHOST=", "+WATCHDOG")) for s in cmd),
                   "Unexpected unreviewed tracing/termination option")
    oracle.require(cmd.count("+AKV_PERF") == int(name == oracle.SKEW), "Original PERF option differs")
    return cmd


def prepare(name, output):
    oracle.require(name in CASES, "carry_illegal and other cases are not eligible")
    output = Path(output).absolute()
    oracle.require(output.parent == OUT and output.resolve() == output and not output.exists(),
                   "Fresh independent direct output required")
    producer, old_budget, budget, elf_sha = CASES[name]
    a = Audit()
    plan_path = OUT / producer / "plan.json"
    plan = a.load(plan_path)
    old = next(c for c in plan["cases"] if c["name"] == name)
    oracle.require(old["elf_sha256"] == elf_sha and old["timeout_s"] == old_budget,
                   "Historical ELF/budget differs")
    oracle.require(plan["simv"] == str(IMAGE) and len(plan["image"]) == 66
                   and plan["image"][str(IMAGE)] == IMAGE_SHA,
                   "Not exact sealed old image66")
    for p, digest in plan["image"].items():
        a.pin(p, digest)
    oracle.require(image_inventory(IMAGE) == plan["image"], "Old image library inventory differs")
    external = []
    for p, digest in old["source_files"].items():
        if Path(p).is_relative_to(ROOT):
            a.pin(p, digest)
        else:
            external.append(p)
    original_root = OUT / producer / "results" / name
    test = original_root / "tests" / ("app_" + name)
    elf_path = a.pin(test / "input.elf", elf_sha)
    actual_path = test / "work/coverage.command.json"
    actual = a.load(actual_path)
    oracle.require([s for s in actual["command"] if s.startswith("+PRELOAD=")] == ["+PRELOAD=" + str(elf_path)],
                   "Original actual ELF preload differs")
    summary = a.load(original_root / "summary.json")
    oracle.require(summary[0]["status"] == "TIMEOUT", "Original TIMEOUT no longer exact")
    a.load(test / "inputs.json")
    a.load(test / "command.json")
    a.pin(test / "commit_trace.csv")
    original_log = a.pin(test / "work/run.vcs.log")
    original_core = a.pin(test / "work/trace_hart_0.log")
    original_privilege = oracle.privilege_log(original_core.read_text())
    config_path = a.pin(IMAGE.parent / "simulator.conf")
    config = dict(line.split("=", 1) for line in config_path.read_text().splitlines() if line and not line.startswith("#"))
    oracle.require(config["sim_l2_bytes"] == "2097152" and config["sim_l2_mb"] == "2"
                   and config["nr_lanes"] == "4" and config["vlen"] == "1024"
                   and config["akv"] == config["akv_v2"] == "1", "Fixed-image configuration differs")
    layout, _ = oracle.elf_layout(elf_path.read_bytes(), 2097152)
    if name == oracle.SKEW:
        static_oracle = oracle.skew.elf_audit(elf_path.read_bytes())
    else:
        static_oracle = dict(checks_formula="23*(4 trap checks+256 halfwords)+3*(1 trap check+256 halfwords)",
                             checks=6751, invalid_descriptor_mutations=23, valid_fill_load_release=3,
                             full_original_software_oracle_unchanged=True)
    history = a.load(OUT / "historical-nonpass-membership-reconciliation-717-20261006-01/audit.json")
    original_group = next(g for g in history["groups"] if g["name"] == name)
    oracle.require(not original_group["run_membership_closed"], "Original no longer unresolved in fixed717 audit")
    for p in (Path(__file__), Path(__file__).with_name("test_run_akv_historical_budget_retry_717.py")):
        a.pin(p.resolve())
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and Path(path).resolve().is_relative_to(ROOT / "verification"):
            a.pin(Path(path).resolve())
    manifest = dict(schema="akv-same-elf-old-image-budget-retry-717-v1", status="PREPARED_PARENT_REVIEW_REQUIRED_NO_RUN",
        case=name, output=str(output), cwd=str(output), input_elf=str(elf_path), elf_sha256=elf_sha,
        command=command_for(actual["command"], output, name), original_command=actual,
        command_changes_allowed=["fresh private ELF path", "fresh commit trace path", "fresh VDB path", "fresh cwd"],
        timeout_s=budget, historical_timeout_s=old_budget, max_cases=1, max_workers=1, automatic_retry=False,
        old_image_files_checked=66, image=plan["image"], static_elf_layout=layout,
        original_privilege_witness=original_privilege, fresh_privilege_witness_required=True,
        software_oracle_static=static_oracle, expected_checks=oracle.CHECKS[name],
        expected_illegal_traps=23 if name == oracle.DESCRIPTOR else 3,
        original_timeout_retained=dict(summary=str(original_root / "summary.json"),
                                       log=str(original_log), trace=str(test / "commit_trace.csv")),
        oracle_gate="Full original software checks + exact ELF/privilege/protocol; skew exact CSR/phase/PERF",
        tool_issue_record=dict(frozen_helper="gap46_akv_oracle.perf_records", issue="FULL translations>=4 rejects measured bare-address translations=0",
                              successor="Existing frozen gap54 perf_records through private gap46 validate_log namespace; no functional check count/phase/CSR/trap change",
                              affects_case=oracle.SKEW, parent_review_required=True),
        excluded_carry=dict(case="vgap35_carry_illegal", retry=False,
                            classification="setup privilege contract issue; not confirmed RTL bug", budget_increase=False),
        environment_review=dict(host_only=True, compiler_runs=False, image_rebuild=False, DVE=False, URG=False,
                                license_settings_unchanged=True, inherited_environment=True,
                                concurrency="One case per independent process; parent chooses serial dispatch to avoid contention",
                                wall_budget_includes_vcs_startup=True,
                                interpreter=sys.executable, python_version=platform.python_version(),
                                external_interpreter_and_stdlib_cryptographic_pins=False),
        external_original_header_pins_not_read=external, pins=a.pins,
        simulations_started=False, coverage_admitted=False, admission_performed=False, rtl_changed=False,
        new_RTL_signoff=False, application_approval=False)
    check_pins(manifest["pins"])
    return output, manifest


def run_reviewed(output, reviewed_seal):
    output = Path(output).absolute()
    record = output.with_name(output.name + ".prepared.json")
    manifest = bound(record, reviewed_seal)
    oracle.require(manifest["case"] in CASES and manifest["output"] == str(output)
                   and manifest["timeout_s"] == CASES[manifest["case"]][2]
                   and manifest["expected_checks"] == oracle.CHECKS[manifest["case"]], "Reviewed identity/budget differs")
    # Reconstruct the entire current contract rather than trusting edited plan fields.
    _, rebuilt = prepare(manifest["case"], output)
    oracle.require(rebuilt == manifest, "Prepared contract no longer exact")
    check_pins(manifest["pins"])
    save(output.with_name(output.name + ".launch-once.json"), dict(prepared_seal=reviewed_seal, case=manifest["case"]))
    output.mkdir()
    save(output / "manifest.json", manifest)
    shutil.copyfile(manifest["input_elf"], output / "input.elf")
    oracle.require(sha(output / "input.elf") == manifest["elf_sha256"], "Private ELF changed")
    status = dict(case=manifest["case"], coverage_admitted=False, admission_performed=False,
                  original_timeout_retained=True, automatic_retry=False)
    process = None
    started = time.monotonic()
    try:
        check_pins(manifest["pins"])
        save(output / "command.json", dict(command=manifest["command"], cwd=str(output), timeout_s=manifest["timeout_s"]))
        with (output / "console.log").open("x") as console:
            process = subprocess.Popen(manifest["command"], cwd=output, stdout=console,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            save(output / "actual-process.json", dict(pid=process.pid, cwd=str(output), command=manifest["command"]))
            try:
                process.wait(timeout=manifest["timeout_s"])
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                status.update(status="TIMEOUT_RETAINED_NOT_ADMITTED", elapsed_s=time.monotonic() - started)
                return status
        status.update(returncode=process.returncode, elapsed_s=time.monotonic() - started)
        log = (output / "console.log").read_text(errors="replace")
        if re.search(r"Core Test \*\*\* FAILED|(?m:^FAILED:)|(?m:^FAIL )", log):
            status["status"] = "DUT_SELFCHECK_FAIL_NOT_ADMITTED"
            return status
        if process.returncode != 0:
            status["status"] = "EXECUTION_ERROR_NOT_AUTOMATIC_DUT_FAIL"
            return status
        proof = oracle.verify(manifest["case"], output, (output / "input.elf").read_bytes(), 2097152)
        save(output / "oracle-result.json", proof)
        status["status"] = "FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED"
        return status
    except Exception as error:
        status.update(status="TOOL_ORACLE_OR_ENVIRONMENT_REJECTED_NOT_DUT_FAIL", reason=f"{type(error).__name__}: {error}")
        return status
    finally:
        # Do not leave child simulations alive on cancellation or evidence exceptions.
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        try:
            check_pins(manifest["pins"])
            oracle.require(sha(output / "input.elf") == manifest["elf_sha256"], "Private ELF drift after execution")
        except Exception as error:
            status.update(status="INPUT_DRIFT_NOT_QUALIFIED", post_run_pin_error=str(error))
        save(output / "terminal.json", status)
        save(output / "result-seal.json", {str(p): sha(p) for p in sorted(output.rglob("*")) if p.is_file()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run-reviewed"))
    parser.add_argument("--case", choices=sorted(CASES))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-seal")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        oracle.require(args.case and args.prepared_seal is None, "Prepare requires only --case")
        output, manifest = prepare(args.case, args.output)
        record = output.with_name(output.name + ".prepared.json")
        save(record, manifest)
        print(json.dumps(dict(status=manifest["status"], prepared=str(record), plan_sha256=sha(record),
                              pins_checked=len(manifest["pins"]), timeout_s=manifest["timeout_s"],
                              expected_checks=manifest["expected_checks"])))
    else:
        oracle.require(args.prepared_seal and args.case is None, "Run-reviewed requires only --prepared-seal")
        print(json.dumps(run_reviewed(args.output, args.prepared_seal)))


if __name__ == "__main__":
    main()
