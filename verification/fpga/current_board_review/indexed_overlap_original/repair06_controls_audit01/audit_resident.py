#!/usr/bin/env python3
"""Read-only resident case audit; no fault-control output or service polling."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
WORKER = OWNER / "repair06_worker"
PREPARED = WORKER / "prepared01"
NAME = "d32m2_i64_resident_ov1"
PLAN_SHA = "d2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8"


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    spec = importlib.util.spec_from_file_location("resident_m6_worker", WORKER / "worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    sha, read, require = worker.sha, worker.read, worker.require
    require(sha(PREPARED / "plan.json") == PLAN_SHA, "Exact M6 plan")
    plan = read(PREPARED / "plan.json")
    worker.validate_plan(plan, worker.IMAGE)
    require(len(plan["pins"]) == 737 and plan["image_sha256"] ==
            "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0", "Image/scope drift")
    ledger, repo, _ = worker.image_context(worker.IMAGE)
    reference = Path(plan["reference"])
    cases, reference_pins = worker.reference_scope(reference)
    require(cases == plan["cases"], "Actual refs03 ELF/helper identity differs")
    case = next(c for c in cases if c["id"] == NAME)
    root = PREPARED / "controls/tests" / NAME
    # A one-time resident-only extract, not a hash or interpretation of a live stage.
    record = None
    pattern = re.compile(r"^\[PASS\s*\]\s+" + re.escape(NAME) + r"\s+(\d+\.\d+)s\s*$")
    with (PREPARED / "service.log").open() as stream:
        for line_number, line in enumerate(stream, 1):
            match = pattern.fullmatch(line.rstrip("\n"))
            if match:
                record = dict(source=str(PREPARED / "service.log"), line_number=line_number,
                    raw_line=line, case=NAME, status="PASS", elapsed_s_rounded=float(match[1]),
                    simulator_rc0_proof="Frozen runner PASS branch plus worker artifacts() rc0 precondition; no separate numeric per-case JSON yet")
                break
    require(record is not None and record["elapsed_s_rounded"] <= case["timeout_s"],
            "No completed resident runner PASS/budget evidence")
    save("resident_runner_record.json", record)
    artifacts = [root / name for name in ("input.elf", "inputs.json", "command.json", "console.log",
        "work/run.vcs.log", "commit_trace.csv", "trace_summary.json", "indexed_analysis.json")]
    before = {str(path): sha(path) for path in artifacts}
    require(sha(root / "input.elf") == sha(reference / NAME / "soc.elf") == case["sha256"], "Private ELF identity")
    require(read(root / "inputs.json") == dict(
        binary=dict(source=case["elf"], path=str(root / "input.elf"), sha256=case["sha256"]),
        simv=dict(path=ledger["simv"], image_sha256=ledger["files"])), "Input/image provenance")
    expected = [ledger["simv"], "-l", "run.vcs.log", "+ntb_random_seed=1", "+PRELOAD=" + str(root / "input.elf"),
        "+TESTCASE=" + NAME, "+NO_FSDB", "+COMMIT_TRACE=" + str(root / "commit_trace.csv"), worker.DEBUG]
    require(read(root / "command.json") == dict(command=expected, cwd=str(root / "work")), "Actual command drift")
    for path in (root / "console.log", root / "work/run.vcs.log"):
        worker.console(case, path.read_text())
    require(read(root / "trace_summary.json")["status"] == "VALID", "Generic trace checker not VALID")
    start = time.monotonic()
    analysis = worker.checker.analyze(root / "commit_trace.csv", reference / NAME, case)
    elapsed = time.monotonic() - start
    save("resident_recomputed_indexed_analysis.json", analysis)
    require(analysis["status"] == "CSV_FULL_ORACLE_PASS", "Raw resident recompute: " + analysis.get("error", ""))
    require(analysis == read(root / "indexed_analysis.json"), "Stored resident analysis differs")
    require(len(analysis["points"]) == 51 and [p["round"] for p in analysis["points"]] == list(range(51)),
            "Missing original50 or masked control")
    require(analysis["checks"] == 5215 and analysis["accepted_targets"] ==
            analysis["successful_target_retires"] == analysis["reloads"] == 51, "Resident full target/reload ledger")
    require(analysis["fault_responses"] == analysis["repairs"] == analysis["retries"] == len(analysis["traps"]) == 0,
            "Unexpected resident faults")
    require(analysis["backing_words_read"] == 32768 and analysis["pte_words_read"] == 1536,
            "Missing full actual scalar backing/PTE reads")
    require(all(sha(path) == value for path, value in before.items()), "Resident artifacts changed during audit")
    worker.common.base.verify_pins(plan["pins"])
    pins = dict(plan["pins"])
    pins.update(reference_pins)
    pins.update(before)
    pins[str(PREPARED / "plan.json")] = PLAN_SHA
    pins[str(HERE / "resident_runner_record.json")] = sha(HERE / "resident_runner_record.json")
    pins[str(HERE / "audit_resident.py")] = sha(HERE / "audit_resident.py")
    runner = repo / "verification/ara_verify/runner.py"
    pins[str(runner)] = sha(runner)
    report = dict(status="RESIDENT_FULL50_PLUS_MASKED_REFERENCE03_INDEPENDENTLY_ACCEPTED", case=NAME,
        same_soc_elf_sha256=case["sha256"], original_linux_elf_sha256=case["original_sha256"],
        plan_sha256=PLAN_SHA, image_sha256=plan["image_sha256"], snapshot_sha256=ledger["snapshot_sha256"],
        plan_pins_verified=737, simulator_exit0_verified_from_completed_frozen_runner=True,
        numeric_per_case_rc_json_present=False, elapsed_s_rounded=record["elapsed_s_rounded"],
        original_artifacts_unchanged=True, raw_analysis_equals_stored=True, recompute_seconds=elapsed,
        rounds=50, extra_original_masked_control=1, full_output_values=1632, guard_values=102,
        checks=5215, accepted_targets=51, successful_target_retires=51, reloads=51,
        faults=0, repairs=0, retries=0, retired=analysis["retired"], last_cycle=analysis["last_cycle"],
        backing_words_read=32768, pte_words_read=1536, whole_controls_stage_accepted=False,
        whole3_accepted=False, worker_service_exit_audited=False, linux_original_schedule_accepted=False,
        fault_control_outputs_or_processes_inspected=False, no_DUT_started=True, no_original_writes=True,
        pins=pins)
    save("resident_audit.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "pins"}))


if __name__ == "__main__":
    main()
