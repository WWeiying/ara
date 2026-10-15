#!/usr/bin/env python3
"""Recompute completed pilot only; never run DUT or write original artifacts."""
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
PREPARED = WORKER / "prepared01"
PLAN_SHA = "d2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"
NAME = "d32m2_i64_fault_ov1"


def save(name, data):
    with (HERE / name).open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    spec = importlib.util.spec_from_file_location("pilot_audit_m6_worker", WORKER / "worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    sha, read, require = worker.sha, worker.read, worker.require
    require(sha(PREPARED / "plan.json") == PLAN_SHA, "Exact M6 plan required")
    plan = read(PREPARED / "plan.json")
    worker.validate_plan(plan, worker.IMAGE)
    require(plan["image_sha256"] == IMAGE_SHA and len(plan["pins"]) == 737, "M6 image/pin membership")
    ledger, _, _ = worker.image_context(worker.IMAGE)
    require(ledger["snapshot_sha256"] == plan["snapshot_sha256"], "Snapshot drift")
    reference = Path(plan["reference"])
    reference_cases, reference_pins = worker.reference_scope(reference)
    require(reference_cases == plan["cases"], "Actual refs03 ELF/helper scope differs")
    case = next(c for c in plan["cases"] if c["id"] == NAME)
    stage = PREPARED / "pilot"
    root = stage / "tests" / NAME
    summary, run = read(stage / "summary.json"), read(stage / "run.json")
    require(len(summary) == 1 and summary[0]["artifact_dir"] == str(root), "Exact pilot artifacts required")
    result = SimpleNamespace(**summary[0])
    worker.common.check_stage([result], run, [case], threading.Event())
    require(result.returncode == 0 and 0 <= result.elapsed_s <= case["timeout_s"], "Pilot simulator exit/budget")
    require(run["jobs"] == 1 and run["tests"] == [NAME] and run["seed"] == 1,
            "Wrong runner stage")
    require(run["invocation"] == [str(WORKER / "worker.py"), "run", "--out", str(PREPARED),
            "--image", str(worker.IMAGE), "--plan-sha256", PLAN_SHA,
            "--unit", "ara-indexed-overlap-m6-01.service", "--authorize-run"], "Runner invocation differs")
    evidence = [stage / "run.json", stage / "summary.json"] + [root / name for name in (
        "input.elf", "inputs.json", "command.json", "console.log", "work/run.vcs.log",
        "commit_trace.csv", "trace_summary.json", "indexed_analysis.json", "work/indexed_first_round.fsdb")]
    before = {str(path): sha(path) for path in evidence}
    require(sha(root / "input.elf") == sha(reference / NAME / "soc.elf") == case["sha256"], "Private same ELF identity")
    require(read(root / "inputs.json") == dict(
        binary=dict(source=case["elf"], path=str(root / "input.elf"), sha256=case["sha256"]),
        simv=dict(path=ledger["simv"], image_sha256=ledger["files"])), "Actual input/image provenance")
    expected = [ledger["simv"], "-l", "run.vcs.log", "+ntb_random_seed=1",
        "+PRELOAD=" + str(root / "input.elf"), "+TESTCASE=" + NAME, "+NO_FSDB",
        "+COMMIT_TRACE=" + str(root / "commit_trace.csv"), worker.DEBUG,
        "-ucli", "-do", str(WORKER / "capture.tcl")]
    require(read(root / "command.json") == dict(command=expected, cwd=str(root / "work")), "Command drift")
    for path in (root / "console.log", root / "work/run.vcs.log"):
        text = path.read_text()
        worker.console(case, text)
        require(text.splitlines().count("INDEXED_PROFILE_CLOSED_AT_1000000NS") == 1,
                "Missing/duplicate actual capture closure line")
    require(read(root / "trace_summary.json")["status"] == "VALID", "Generic trace not VALID")
    require((root / "work/indexed_first_round.fsdb").stat().st_size > 1024, "Missing waveform")
    started = time.monotonic()
    analysis = worker.checker.analyze(root / "commit_trace.csv", reference / NAME, case)
    recompute_seconds = time.monotonic() - started
    save("recomputed_indexed_analysis.json", analysis)
    require(analysis["status"] == "CSV_FULL_ORACLE_PASS", "Recompute failed: " + analysis.get("error", ""))
    stored = read(root / "indexed_analysis.json")
    require(analysis == stored, "Recomputed and original analysis differ")
    require(len(analysis["points"]) == 50 and [point["round"] for point in analysis["points"]] == list(range(50)),
            "Full fifty-point membership")
    require(analysis["checks"] == 21595 and analysis["accepted_targets"] == 1650 and
            analysis["reloads"] == analysis["successful_target_retires"] == 50 and
            analysis["fault_responses"] == analysis["repairs"] == analysis["retries"] == len(analysis["traps"]) == 1600,
            "Full accepted/fault/retry/retire totals")
    require(analysis["backing_words_read"] == 32768 and analysis["pte_words_read"] == 1536 and
            analysis["points"][0]["cycle"] < 950000, "Full memory/PTE/first capture scope")
    require(all(sha(path) == digest for path, digest in before.items()), "Pilot evidence changed during audit")
    worker.common.base.verify_pins(plan["pins"])
    wave_path = OWNER / "repair06_wave_audit01/audit.json"
    require(sha(wave_path) == "5f04d24076dbcbbc8e86bde8426393416d137de21f1fd711fc047ede9b4f3427", "Independent wave finding changed")
    wave = read(wave_path)
    require(wave["status"] == "BOUNDED_WAVE_INDEPENDENTLY_CONFIRMED_NOT_FULL50" and
            wave["mmu_va"] == "0x40017000", "Old failure path not measured correct")
    require(str(root / "input.elf") in wave["pins"] and wave["pins"][str(root / "input.elf")] == case["sha256"],
            "Wave and full pilot ELF do not bind")
    immutable_pins = dict(plan["pins"])
    immutable_pins.update(reference_pins)
    immutable_pins.update(before)
    immutable_pins[str(PREPARED / "plan.json")] = PLAN_SHA
    immutable_pins[str(wave_path)] = sha(wave_path)
    immutable_pins[str(HERE / "audit.py")] = sha(HERE / "audit.py")
    report = dict(status="PILOT_FULL50_SV39_REFERENCE03_INDEPENDENTLY_ACCEPTED", name=NAME,
        same_soc_elf_sha256=case["sha256"], authentic_original_linux_elf_sha256=case["original_sha256"],
        plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, snapshot_sha256=ledger["snapshot_sha256"],
        plan_pin_count=len(plan["pins"]), simulator_returncode=result.returncode, elapsed_s=result.elapsed_s,
        runner_status=run["status"], runner_counts=run["status_counts"], recompute_seconds=recompute_seconds,
        raw_csv_equals_stored_analysis=True, original_evidence_unchanged=True,
        rounds=50, outputs=1600, guards=100, checks=analysis["checks"], accepted_targets=analysis["accepted_targets"],
        reloads=analysis["reloads"], successful_target_retires=analysis["successful_target_retires"],
        faults=analysis["fault_responses"], repairs=analysis["repairs"], retries=analysis["retries"],
        retired=analysis["retired"], last_cycle=analysis["last_cycle"], backing_words_read=32768, pte_words_read=1536,
        bounded_wave_causal_path_confirmed=True, whole_three_cases_accepted=False, worker_or_service_exit_audited=False,
        linux_original_fault_schedule_accepted=False, no_DUT_started=True, no_original_writes=True, pins=immutable_pins)
    save("audit.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "pins"}))


if __name__ == "__main__":
    main()
