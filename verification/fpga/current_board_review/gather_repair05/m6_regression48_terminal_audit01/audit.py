#!/usr/bin/env python3
"""Offline exact48 acceptance and byte-exact16 controls; never launch or poll."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
OUT = OWNER / "repair06_regression48_prepared01"
PLAN_SHA = "ac33642809800f58c5f4534bdb52622849335ee3872a2b4347da7b7588ff8929"
IMAGE_SHA = "a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0"
COORD = OWNER.parent / "indexed_overlap_original/repair06_followup"
COORD_PLAN_SHA = "ee0b810e5bcd99cb7d2727923628a35b202db3c66219b7fac96966bf2a1124d4"


def save(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def same_bytes(left, right):
    size = 0
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            x, y = a.read(1048576), b.read(1048576)
            if x != y:
                raise ValueError("Complete control CSV bytes differ: " + str(right))
            size += len(x)
            if not x:
                return size


def main():
    spec = importlib.util.spec_from_file_location("m6_reg48_frozen_helper", OWNER / "regression.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    read, require = worker.read, worker.require
    sha = lambda path: worker.sha(Path(path))
    require(sha(OUT / "plan.json") == PLAN_SHA, "Exact sealed regression plan")
    plan = read(OUT / "plan.json")
    image = Path(plan["image"])
    worker.validate_plan(plan, image)
    require(len(plan["pins"]) == 755 and plan["image_sha256"] == IMAGE_SHA, "M6/755 pin scope")
    ledger, _, _ = worker.image_context(image)
    require(Path(ledger["snapshot"]).parent.name == "current_board_memory_candidate06" and
            ledger["snapshot_sha256"] == plan["snapshot_sha256"], "Frozen M6 snapshot")
    terminal = read(OUT / "complete.json")
    require(terminal["status"] == "PASS_48_ARCHITECTURAL" and terminal["aborted"] is False and
            terminal["pins_unchanged"] is True and terminal["plan_sha256"] == PLAN_SHA and
            terminal["image_sha256"] == IMAGE_SHA and terminal["image"] == str(image), "False/foreign terminal")
    cases, controls, reference_pins = worker.original_scope()
    require(cases == plan["cases"] and controls == plan["controls"] and len(cases) == 48 and len(controls) == 16,
            "Original inventory exact membership")
    require(len({c["id"] for c in cases}) == len({c["sha256"] for c in cases}) == 48, "Duplicate member/ELF")
    results = terminal["results"]
    require(len(results) == 48 and {r["name"] for r in results} == {c["id"] for c in cases}, "Missing/duplicate result")
    expected_evidence = set()
    control_ids = {c["id"] for c in controls}
    for stage in plan["stages"]:
        selected = [c for c in cases if c["stage"] == stage["name"]]
        records = [r for r in results if r["name"] in {c["id"] for c in selected}]
        metadata = read(OUT / stage["name"] / "run.json")
        worker.check_stage([SimpleNamespace(**r) for r in records], metadata, selected, threading.Event())
        require(metadata["jobs"] == stage["jobs"] and metadata["tests"] == [c["id"] for c in selected] and
                metadata["seed"] == 1 and metadata["config"] == "default" and metadata["simv"] == ledger["simv"] and
                metadata["commit_trace"] is True and metadata["code_coverage"] is False and metadata["completed_at"],
                "Stage actual contract differs")
        require(read(OUT / stage["name"] / "summary.json") == records, "Stage summary differs from terminal")
        expected_evidence.update(str(OUT / stage["name"] / f) for f in ("run.json", "summary.json"))
        for case in selected:
            root = OUT / stage["name"] / "tests" / case["id"]
            expected_evidence.update(str(root / f) for f in ("input.elf", "inputs.json", "command.json",
                "console.log", "work/run.vcs.log", "commit_trace.csv", "trace_summary.json"))
            if case["id"] in control_ids:
                expected_evidence.update(str(root / f) for f in ("performance.json", "cycle_differences.csv"))
    require(len(expected_evidence) == 372 and set(terminal["evidence_pins"]) == expected_evidence, "Exact372 evidence")
    worker.base.verify_pins(terminal["evidence_pins"])
    before = dict(terminal["evidence_pins"])
    before[str(OUT / "complete.json")] = sha(OUT / "complete.json")
    cases_report = []
    for case in cases:
        data = next(r for r in results if r["name"] == case["id"])
        root = OUT / case["stage"] / "tests" / case["id"]
        require(data["artifact_dir"] == str(root) and data["status"] == "PASS" and data["returncode"] == 0 and
                not data["reason"], "Case identity/exit/terminal")
        worker.check_artifacts(SimpleNamespace(**dict(data, artifact_dir=root)), case, ledger)
        for path in (root / "console.log", root / "work/run.vcs.log"):
            worker.check_console(case, path.read_text())
        cases_report.append(dict(id=case["id"], stage=case["stage"], group=case["group"],
            elf_sha256=case["sha256"], returncode=0, elapsed_s=data["elapsed_s"], timeout_s=case["timeout_s"],
            original_oracle_and_both_logs_pass=True, private_input_and_command_verified=True,
            generic_trace_summary=read(root / "trace_summary.json")))
    base_root = OWNER.parent / "comparison_alias_original/candidate04_01"
    base_plan, base_terminal = read(base_root / "plan.json"), read(base_root / "complete.json")
    require(base_terminal["status"] == "PASS_19_PLUS_16", "Old baseline acceptance identity")
    base_image = Path(base_plan["image"])
    require(sha(base_image / "image.json") == base_plan["image_sha256"] ==
            base_plan["pins"][str(base_image / "image.json")], "Pinned M4 image identity")
    base_ledger = read(base_image / "image.json")
    require(base_ledger["configuration_sha256"] == ledger["configuration_sha256"] ==
            sha(Path(base_ledger["simv"]).parent / "simulator.conf"), "Baseline/M6 actual same configuration")
    comparisons = []
    for control in controls:
        case = next(c for c in cases if c["id"] == control["id"])
        root = OUT / case["stage"] / "tests" / case["id"]
        old_csv, current = Path(control["baseline_csv"]), root / "commit_trace.csv"
        old = old_csv.parent
        old_inputs = read(old / "inputs.json")
        require(sha(old / "input.elf") == case["sha256"] == old_inputs["binary"]["sha256"] and
                old_inputs["binary"]["path"] == str(old / "input.elf") and
                old_inputs["simv"] == dict(path=base_ledger["simv"], image_sha256=base_ledger["files"]),
                "Baseline control same ELF/image input")
        require(read(old / "command.json") == dict(command=[base_ledger["simv"], "-l", "run.vcs.log",
            "+ntb_random_seed=1", "+PRELOAD=" + str(old / "input.elf"), "+TESTCASE=" + case["original_name"],
            "+NO_FSDB", "+COMMIT_TRACE=" + str(old_csv)], cwd=str(old / "work")), "Baseline command differs")
        require(read(old / "trace_summary.json")["status"] == "VALID", "Old trace not VALID")
        old_marker_lines = worker.oracle_lines((old / "console.log").read_text())
        for log in (root / "console.log", root / "work/run.vcs.log"):
            require(worker.oracle_lines(log.read_text()) == old_marker_lines, "Control oracle sequence changed")
        size = same_bytes(old_csv, current)
        rows, retired, last_cycle = 0, 0, None
        with current.open(newline="") as stream:
            reader = csv.DictReader(stream)
            require("cycle" in reader.fieldnames, "No cycle field in complete CSV")
            for row in reader:
                rows += 1
                retired += row["event"] == "retire"
                last_cycle = int(row["cycle"])
        require(rows > 0, "Empty control CSV")
        expected = dict(rows=rows, cycle_changed_rows=0, noncycle_equal=True, last_cycle_delta=0,
                        differences=str(root / "cycle_differences.csv"))
        require(terminal["performance"][case["id"]] == read(root / "performance.json") == expected,
                "Recorded performance differs from actual full CSV")
        with (root / "cycle_differences.csv").open(newline="") as stream:
            require(list(csv.reader(stream)) == [["row", "event", "order", "baseline_cycle", "current_cycle", "delta"]],
                    "Unexpected recorded cycle differences")
        comparisons.append(dict(id=case["id"], elf_sha256=case["sha256"], baseline_csv=str(old_csv),
            current_csv=str(current), baseline_and_current_csv_sha256=sha(current), bytes=size,
            rows=rows, retired=retired, last_cycle=last_cycle, byte_equal_including_cycles=True,
            cycle_changed_rows=0, noncycle_equal=True, same_default_configuration=True, same_seed=1))
    require(set(terminal["performance"]) == control_ids and terminal["performance_status"] == "EXACT_16_CSV",
            "Performance exact sixteen membership")
    coord_out = COORD / "fresh02"
    require(sha(coord_out / "plan.json") == COORD_PLAN_SHA and sha(COORD / "coordinator_successor.py") ==
            "a78191e2e8288318fbebf67612a69ed71f2f799ec0bb11825f2e7fac15d3c130", "Reviewed coordinator identity")
    coord_plan, coord_end, child = read(coord_out / "plan.json"), read(coord_out / "complete.json"), read(coord_out / "child.json")
    require(coord_end["status"] == "REGRESSION48_PASS" and coord_end["aborted"] is False and
            coord_end["plan_sha256"] == COORD_PLAN_SHA and coord_end["image_sha256"] == IMAGE_SHA and
            coord_end["regression"]["terminal_sha256"] == sha(OUT / "complete.json") and
            coord_end["regression"]["evidence_pins"] == terminal["evidence_pins"] and
            coord_end["regression"]["evidence_count"] == 372 and coord_end["regression"]["results"] == 48,
            "Coordinator did not accept this exact regression")
    require(child["pid"] == 675396 and child["command"] == coord_plan["command"] ==
            ["/usr/bin/python3", "-B", str(OWNER / "regression.py"), "run", "--image", str(image),
             "--out", str(OUT), "--plan-sha256", PLAN_SHA, "--authorize-run"] and
            child["cgroup"].endswith("/" + coord_plan["unit"]) and child["new_service"] is False, "Actual child identity")
    for path in (coord_out / "plan.json", coord_out / "complete.json", coord_out / "child.json",
                 coord_out / "launch.json", COORD / "coordinator_successor.py", base_root / "plan.json",
                 base_root / "complete.json", base_image / "image.json", Path(base_ledger["simv"]).parent / "simulator.conf"):
        before[str(path)] = sha(path)
    require(all(sha(path) == digest for path, digest in before.items()), "Terminal/raw evidence changed")
    worker.base.verify_pins(plan["pins"])
    pins = dict(plan["pins"])
    pins.update(reference_pins)
    pins.update(before)
    pins[str(OUT / "plan.json")] = PLAN_SHA
    pins[str(HERE / "audit.py")] = sha(HERE / "audit.py")
    report = dict(status="M6_EXACT48_DUT_CASES_ACCEPTED_16_FULL_CSV_BYTE_IDENTICAL", plan_sha256=PLAN_SHA,
        image_sha256=IMAGE_SHA, snapshot_sha256=ledger["snapshot_sha256"], configuration_sha256=ledger["configuration_sha256"],
        plan_pins_verified=755, evidence_pins_verified=372, exact_members=48, distinct_ELFs=48,
        stages=[dict(name=s["name"], jobs=s["jobs"], cases=sum(c["stage"] == s["name"] for c in cases)) for s in plan["stages"]],
        cases=cases_report, controls=comparisons, control_full_bytes_identical=16, original_artifacts_unchanged=True,
        baseline_image_sha256=base_plan["image_sha256"], baseline_acceptance="REUSED_PINNED_M4_PASS_19_PLUS_16",
        coordinator_child_pid=child["pid"], coordinator_parent_pid=child["parent"],
        child_returncode0_inferred_from_pinned_coordinator_terminal=True, standalone_child_wait_status_saved=False,
        case_returncodes_actual_numeric=[r["returncode"] for r in results],
        outer_service_actual_exit="UNAVAILABLE_AFTER_PARENT_REPORTED_GC", outer_service_exit0_verified=False,
        GC_or_missing_child_used_as_positive_exit_evidence=False, performance_scope="Only these16 identical programs/config/seed/full CSV normal controls",
        all_workload_performance_claim=False, live_e8_queried=False, processes_or_services_queried=False,
        no_DUT_or_Host_rerun=True, no_original_or_sealed_writes=True, pins=pins)
    save("audit.json", report)
    save("controls16.json", comparisons)
    print(json.dumps({key: value for key, value in report.items() if key not in ("pins", "cases", "controls")}))


if __name__ == "__main__":
    main()
