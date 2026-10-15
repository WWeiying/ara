#!/usr/bin/env python3
"""Whole3 offline acceptance: reuse two independent audits, recompute fault ov0."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
WORKER = OWNER / "repair06_worker"
OUT = WORKER / "prepared01"
PLAN_SHA = "d2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"


def save(name, data):
    with (HERE / name).open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    spec = importlib.util.spec_from_file_location("whole3_m6_sealed_worker", WORKER / "worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    read, require = worker.read, worker.require
    sha = lambda path: worker.sha(Path(path))
    require(sha(OUT / "plan.json") == PLAN_SHA, "Exact M6 plan")
    plan = read(OUT / "plan.json")
    worker.validate_plan(plan, worker.IMAGE)
    require(len(plan["pins"]) == 737 and plan["image_sha256"] == IMAGE_SHA, "737/M6 identity")
    ledger, repo, _ = worker.image_context(worker.IMAGE)
    require(ledger["snapshot_sha256"] == plan["snapshot_sha256"] and ledger["configuration_sha256"] ==
            "6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785", "Snapshot/config drift")
    reference = Path(plan["reference"])
    reference_cases, reference_pins = worker.reference_scope(reference)
    require(reference_cases == plan["cases"], "Actual refs03 ELFs/original41 helper drift")
    terminal = read(OUT / "complete.json")
    require(terminal["status"] == "PASS_3_REFERENCE03_FULL50_M6" and terminal["aborted"] is False and
            terminal["pins_unchanged"] is True and terminal["plan_sha256"] == PLAN_SHA and
            terminal["image_sha256"] == IMAGE_SHA and 0 <= terminal["elapsed_s"] < 8800,
            "Wrong/incomplete/late terminal")
    results = terminal["results"]
    require(len(results) == 3 and [r["name"] for r in results] == list(worker.NAMES), "Exact three membership/order")
    expected_evidence = set()
    for stage in plan["stages"]:
        names = stage["cases"]
        records = [r for r in results if r["name"] in names]
        metadata = read(OUT / stage["name"] / "run.json")
        require(read(OUT / stage["name"] / "summary.json") == records, "Stage summary/terminal mismatch")
        worker.common.check_stage([SimpleNamespace(**r) for r in records], metadata,
            [c for c in plan["cases"] if c["id"] in names], threading.Event())
        require(metadata["tests"] == names and metadata["jobs"] == stage["jobs"] and
                metadata["simv"] == ledger["simv"] and metadata["seed"] == 1 and
                metadata["commit_trace"] is True and metadata["code_coverage"] is False, "Actual runner contract")
        expected_evidence.update(str(OUT / stage["name"] / f) for f in ("run.json", "summary.json"))
        for name in names:
            root = OUT / stage["name"] / "tests" / name
            expected_evidence.update(str(root / f) for f in ("input.elf", "inputs.json", "command.json", "console.log",
                "work/run.vcs.log", "commit_trace.csv", "trace_summary.json", "indexed_analysis.json"))
            if stage["name"] == "pilot":
                expected_evidence.add(str(root / "work/indexed_first_round.fsdb"))
    require(set(terminal["evidence_pins"]) == expected_evidence and len(expected_evidence) == 29,
            "Exact29 raw terminal evidence required")
    worker.common.base.verify_pins(terminal["evidence_pins"])
    before = dict(terminal["evidence_pins"])
    before[str(OUT / "complete.json")] = sha(OUT / "complete.json")
    before[str(OUT / "launch.json")] = sha(OUT / "launch.json")
    prior_specs = {
        worker.NAMES[0]: (OWNER / "repair06_pilot_audit01/audit.json",
            "5fa09acc481a69c1e0968b261fadab68883df9d320a8f425824ecebe4bc8ce42",
            OWNER / "repair06_pilot_audit01/recomputed_indexed_analysis.json",
            "PILOT_FULL50_SV39_REFERENCE03_INDEPENDENTLY_ACCEPTED"),
        worker.NAMES[1]: (OWNER / "repair06_controls_audit01/resident_audit.json",
            "56f9a2dedeac9806a55cb8a800fecbefb8ad809c9b787afe25f0061f5bd50e19",
            OWNER / "repair06_controls_audit01/resident_recomputed_indexed_analysis.json",
            "RESIDENT_FULL50_PLUS_MASKED_REFERENCE03_INDEPENDENTLY_ACCEPTED"),
    }
    bindings = dict(plan["pins"])
    bindings.update(reference_pins)
    case_reports = []
    for case in plan["cases"]:
        name = case["id"]
        stage = "pilot" if name == worker.NAMES[0] else "controls"
        root = OUT / stage / "tests" / name
        result = next(r for r in results if r["name"] == name)
        require(result["status"] == "PASS" and result["returncode"] == 0 and not result["reason"] and
                result["artifact_dir"] == str(root) and 0 <= result["elapsed_s"] <= case["timeout_s"], "Case exit/identity/budget")
        for log in (root / "console.log", root / "work/run.vcs.log"):
            worker.console(case, log.read_text())
        require(sha(root / "input.elf") == case["sha256"], "Private ELF drift")
        require(read(root / "inputs.json") == dict(
            binary=dict(source=case["elf"], path=str(root / "input.elf"), sha256=case["sha256"]),
            simv=dict(path=ledger["simv"], image_sha256=ledger["files"])), "Actual inputs/image differ")
        command = [ledger["simv"], "-l", "run.vcs.log", "+ntb_random_seed=1", "+PRELOAD=" + str(root / "input.elf"),
            "+TESTCASE=" + name, "+NO_FSDB", "+COMMIT_TRACE=" + str(root / "commit_trace.csv"), worker.DEBUG]
        if stage == "pilot":
            command += ["-ucli", "-do", plan["pilot_capture"]]
        require(read(root / "command.json") == dict(command=command, cwd=str(root / "work")), "Actual command differs")
        require(read(root / "trace_summary.json")["status"] == "VALID", "Generic trace not VALID")
        if name in prior_specs:
            path, digest, recomputed, status = prior_specs[name]
            require(sha(path) == digest, "Prior independent audit changed")
            prior = read(path)
            require(prior["status"] == status and prior["plan_sha256"] == PLAN_SHA and
                    prior["image_sha256"] == IMAGE_SHA and prior["same_soc_elf_sha256"] == case["sha256"], "Prior case binding")
            for evidence_path, evidence_hash in prior["pins"].items():
                if evidence_path in terminal["evidence_pins"]:
                    require(terminal["evidence_pins"][evidence_path] == evidence_hash, "Prior raw evidence differs")
            require(sha(recomputed) == sha(root / "indexed_analysis.json"), "Prior raw recompute/stored analysis changed")
            analysis, elapsed, method = read(recomputed), None, "REUSED_HASH_BOUND_INDEPENDENT_RAW_AUDIT"
            bindings[str(path)] = digest
            bindings[str(recomputed)] = sha(recomputed)
        else:
            started = time.monotonic()
            analysis = worker.checker.analyze(root / "commit_trace.csv", reference / name, case)
            elapsed, method = time.monotonic() - started, "NEW_RAW_CSV_RECOMPUTE"
            save("fault_ov0_recomputed_indexed_analysis.json", analysis)
        require(analysis == read(root / "indexed_analysis.json") and analysis["status"] == "CSV_FULL_ORACLE_PASS",
                "Raw analysis does not equal stored full oracle")
        count, faults = (50, 1600) if case["fault"] else (51, 0)
        require(analysis["rounds"] == 50 and len(analysis["points"]) == count and
                [p["round"] for p in analysis["points"]] == list(range(count)) and
                analysis["checks"] == case["checks"] and analysis["reloads"] == analysis["successful_target_retires"] == count and
                analysis["accepted_targets"] == count + faults and analysis["fault_responses"] ==
                analysis["repairs"] == analysis["retries"] == len(analysis["traps"]) == faults and
                analysis["backing_words_read"] == 32768 and analysis["pte_words_read"] == 1536, "Incomplete oracle counters")
        case_reports.append(dict(name=name, returncode=0, elapsed_s=result["elapsed_s"], checks=analysis["checks"],
            rounds=50, complete_points=count, output_values=count * 32, guards=count * 2,
            reloads=count, accepted_targets=count + faults, successful_target_retires=count,
            faults=faults, repairs=faults, retries=faults, retired=analysis["retired"], last_cycle=analysis["last_cycle"],
            soc_elf_sha256=case["sha256"], original_linux_elf_sha256=case["original_sha256"],
            raw_analysis_equals_stored=True, raw_audit_method=method, recompute_seconds=elapsed))
    witness = OWNER / "repair06_exit_witness01"
    startup, exit_record = read(witness / "run01/startup.json"), read(witness / "run01/actualexit.json")
    facts, launch = exit_record["properties"], read(OUT / "launch.json")
    require(startup["plan"] == str(OUT / "plan.json") and startup["plan_sha256"] == PLAN_SHA and
            launch["plan_sha256"] == PLAN_SHA and launch["pid"] == 620452, "Witness/launch original plan owner")
    for initial in (startup["before"], startup["after_ref"]):
        require(initial["Id"] == launch["service"]["Id"] == "ara-indexed-overlap-m6-01.service" and
                initial["LoadState"] == "loaded" and initial["ActiveState"] == "active" and
                initial["MainPID"] == initial["ExecMainPID"] == launch["pid"] and
                initial["ControlGroup"] == launch["service"]["ControlGroup"] and
                initial["InvocationID"] == "94f592605b7147d3b5e47923457f3078" and
                initial["ExecMainStartTimestamp"] == facts["ExecMainStartTimestamp"], "Witness startup generation/cgroup")
    require(exit_record["kind"] == "SYSTEMD_EXIT_FACTS_ONLY" and exit_record["exit_evidence_complete"] is True and
            facts["Id"] == startup["before"]["Id"] and facts["LoadState"] == "loaded" and
            facts["InvocationID"] == startup["before"]["InvocationID"] and
            facts["ActiveState"] == "inactive" and facts["SubState"] == "dead" and facts["MainPID"] == 0 and
            facts["ExecMainPID"] == 620452 and facts["ExecMainCode"] == 1 and facts["ExecMainStatus"] == 0 and
            facts["Result"] == "success", "Actual exit0 facts missing/wrong generation")
    start_s, end_s = facts["ExecMainStartTimestamp"] / 1000000, facts["ExecMainExitTimestamp"] / 1000000
    require(start_s < launch["started"] < terminal["finished"] <= end_s <= facts["observed_unix"] and
            0 < end_s - start_s < plan["service_seconds"], "Actual exit timestamps/bound")
    for path in (witness / "witness.py", witness / "test_witness.py", witness / "README.md",
                 witness / "run01/startup.json", witness / "run01/actualexit.json"):
        before[str(path)] = sha(path)
    require(all(sha(path) == digest for path, digest in before.items()), "Terminal/original evidence changed")
    worker.common.base.verify_pins(plan["pins"])
    bindings.update(before)
    bindings[str(OUT / "plan.json")] = PLAN_SHA
    for path in (HERE / "audit.py", HERE / "fault_ov0_recomputed_indexed_analysis.json"):
        bindings[str(path)] = sha(path)
    report = dict(status="WHOLE3_REFERENCE03_M6_INDEPENDENTLY_ACCEPTED_WITH_ACTUAL_WORKER_EXIT0",
        plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, snapshot_sha256=ledger["snapshot_sha256"],
        configuration_sha256=ledger["configuration_sha256"], plan_pins_verified=737, terminal_evidence_pins_verified=29,
        terminal_aborted=False, worker_elapsed_s=terminal["elapsed_s"], cases=case_reports,
        actual_exit_facts=facts, actual_service_elapsed_s=end_s - start_s, worker_exit0_verified=True,
        witness_is_functional_oracle=False, witness_generation_bound_to_original_launch=True,
        GC_default_success_used=False, original_artifacts_unchanged=True, linux_original_schedule_accepted=False,
        regression48_functional_or_performance_accepted=False, live48_or_e8_queried=False,
        new_DUT_or_service_queries=False, no_DUT_started=True, no_original_or_sealed_writes=True, pins=bindings)
    save("audit.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "pins"}))


if __name__ == "__main__":
    main()
