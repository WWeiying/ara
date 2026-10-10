#!/usr/bin/env python3
"""Extend original-image 473 PASS coverage; never mix repaired-image VDBs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import extend_memory_coverage as memory
import archive_original_coverage_sources as archive

batch, base = memory.b, memory.b.base
extension, gap, current = memory.extension, memory.gap, memory.current
ROOT, HERE = batch.ROOT, batch.HERE
SCRIPT = Path(__file__).resolve()
BASELINE = ROOT / "verification/out/vcs-memory-gap-20260928-01"
IMAGE_DIR = ROOT / "verification/out/repair-closure-coverage-20260927-01"
MANIFEST = IMAGE_DIR / "sim/vcs_source_manifest.json"
PREDECESSOR_UNIT = "ara-memory-vl0-repair-regression-20260928-01.service"
SELECTION = ROOT / "verification/tests/rvv_queue_gap28_selection.json"
READY = ROOT / "verification/tests/rvv_queue_gap28_ready.json"
ORIGINAL_FROZEN = batch.frozen
QUEUE = None
read, save, check, pins = batch.read, batch.save, batch.check, batch.pins
require = current.require


def original_sources(manifest_path):
    # Old-version validator: never interpret live patched RTL as original.
    require(Path(manifest_path) == MANIFEST, "unexpected source-manifest validation request")
    return archive.validate(QUEUE / "original-sources", MANIFEST)


def frozen(output, case=None, all_cases=False):
    if output == BASELINE:
        check(read(output / "plan.sha256.json"))
        original = read(output / "plan.json")
        original_sources(MANIFEST)
        record = read(QUEUE / "original-sources/archive.json")
        plan = dict(original, files=archive.archived_pins(original["files"], record),
                    cases=[dict(c, source_files=archive.archived_pins(c["source_files"], record))
                           for c in original["cases"]])
        check(plan["files"])
        require(batch.simulation_image(Path(plan["simv"])) == plan["image"], "original image inventory drift")
        require(batch.simulation_image(Path(plan["wrapper"])) == plan["wrapper_image"], "baseline wrapper drift")
        if all_cases:
            for row in plan["cases"]:
                check(row["source_files"])
        return plan
    plan = ORIGINAL_FROZEN(output, case, all_cases)
    require(plan["simv"] == str(IMAGE_DIR / "sim/simv"), "repaired/foreign image rejected")
    if all_cases:
        original_sources(MANIFEST)
        require(batch.simulation_image(Path(plan["simv"])) == plan["image"], "original image inventory drift")
    return plan


def prepare(output, selection, ready):
    check(read(QUEUE / "bootstrap.json")["files"])
    state = read(BASELINE / "checkpoint.json")
    require(state["status"] == "COMPLETE_WITH_FAILURES" and state["completed"] == state["total"] == 485 and
            state["passed"] == 473, "expected immutable 473-PASS/12-TIMEOUT baseline")
    proof = read(ready)
    require(proof["status"] == "READY", "Curie readiness not confirmed")
    require(Path(proof["selection"]).resolve() == selection, "READY selection differs")
    check(proof["files"])
    require(str(selection) in proof["files"], "READY must pin the selection")
    names = read(selection)["tests"]
    require(len(names) == len(set(names)) == 36 and all(n.startswith("rvv:vqueue_gap28_") for n in names),
            "expected Curie's exact 36-case matrix")
    for name in names:
        stem = name.split(":", 1)[1]
        for path in (ROOT / "apps/bin" / ("rv64uv-ara-" + stem),
                     ROOT / "apps/riscv-tests/isa/rv64uv" / (stem + ".c")):
            require(str(path) in proof["files"], f"READY does not pin {path}")
    # Copy all original outcomes without rerunning them; only PASS VDBs enter DVE.
    extension.select_tests = gap.select_tests
    gap.prepare(output, BASELINE, selection)
    plan = read(output / "plan.json")
    plan["files"].update(proof["files"])
    plan["files"].update(pins([ready, SCRIPT, Path(archive.__file__), QUEUE / "bootstrap.json",
                               QUEUE / "original-sources/archive.json", QUEUE / "original-sources/archive.sha256.json"]))
    plan.update(policy="CONTINUE_FUNCTIONAL_FAILURE_STOP_INFRASTRUCTURE",
        evidence_version="ORIGINAL_PRE_SEGMENT_VL0_REPAIR_IMAGE", current_rtl_claim=False,
        repaired_vdb_reuse=False, archived_sources=str(QUEUE / "original-sources/archive.json"))
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    frozen(output, all_cases=True)


def summarize(output, plan):
    outcomes = memory.summarize(output, plan)
    path = output / "collection.json"
    result = read(path)
    result.update(evidence_version="ORIGINAL_PRE_SEGMENT_VL0_REPAIR_IMAGE", current_rtl_claim=False,
        repaired_vdb_reuse=False, baseline_passed=473, added_passed=result["passed"] - 473,
        source_archive=plan["archived_sources"], original_image=plan["simv"],
        known_original_failures_retained=12)
    save(path, result)
    return outcomes


def predecessor_stopped(unit):
    result = subprocess.run(["systemctl", "--user", "show", unit,
        "-p", "ActiveState", "-p", "MainPID"], capture_output=True, text=True, check=True, timeout=10)
    state = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if state.get("ActiveState") in ("active", "activating", "deactivating"):
        return False
    require(state.get("MainPID") == "0", "predecessor main process remains")
    base.quiescent_build(unit)
    return True


def queue(output, selection, ready, unit):
    base.check_service()
    require(not output.exists(), "new exploration output required")
    QUEUE.mkdir(parents=True, exist_ok=False)
    check(read(BASELINE / "plan.sha256.json"))
    original = read(BASELINE / "plan.json")
    require(original["simv"] == str(IMAGE_DIR / "sim/simv"), "baseline is not original image")
    check(original["image"])
    snapshot = archive.snapshot(MANIFEST, QUEUE / "original-sources", original["image"])
    files = pins(current.tool_paths() + [SCRIPT, Path(archive.__file__), BASELINE / "plan.json",
                                        BASELINE / "plan.sha256.json", BASELINE / "checkpoint.json"])
    files.update({r["archive"]: r["sha256"] for r in snapshot["files"]})
    files.update(original["image"])
    save(QUEUE / "bootstrap.json", {"files": files, "selection": str(selection), "ready": str(ready),
          "previous_unit": unit, "baseline": str(BASELINE), "evidence_version": snapshot["scope"]})
    state = {"status": "WAITING", "phase": "repair-quiescence-and-Curie-READY", "simulations_started": False,
             "selection": str(selection), "ready": str(ready), "workers": 8, "original_image": original["simv"],
             "current_rtl_claim": False, "repaired_vdb_reuse": False}
    save(QUEUE / "status.json", state)
    deadline = time.monotonic() + 14400
    try:
        while not predecessor_stopped(unit) or not ready.is_file():
            require(time.monotonic() < deadline, "four-hour predecessor/READY wait expired")
            time.sleep(30)
        check(files)
        state.update(status="PREPARING", phase="freeze-Curie-inputs-original-image")
        save(QUEUE / "status.json", state)
        prepare(output, selection, ready)
        state.update(status="HANDED_OFF", phase="eight-worker-exploration", checkpoint=str(output / "checkpoint.json"))
        save(QUEUE / "status.json", state)
        return batch.execute(output, 8)
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
        save(QUEUE / "status.json", state)
        raise


def main():
    global QUEUE
    batch.SCRIPT, extension.SCRIPT = SCRIPT, SCRIPT
    batch.frozen, batch.summarize = frozen, summarize
    # Restore exploration scheduling instead of the imported serial repair gate.
    batch.schedule = memory.original_schedule
    base.sources = original_sources
    if len(sys.argv) > 2 and sys.argv[1] == "--coverage-exec":
        argv = batch.adapter_command(read(sys.argv[2]), sys.argv[3:], Path.cwd().resolve())
        with Path("coverage.command.json").open("x") as stream:
            json.dump({"command": argv, "cwd": str(Path.cwd())}, stream)
        os.execv(argv[0], argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=SELECTION)
    parser.add_argument("--ready", type=Path, default=READY)
    parser.add_argument("--previous-unit", default=PREDECESSOR_UNIT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--worker")
    modes.add_argument("--directed")
    args = parser.parse_args()
    output = base.checked_output(args.output)
    QUEUE = output.with_name(output.name + "-queue")
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return batch.worker(output, args.worker)
    if args.directed:
        return batch.directed(output, args.directed)
    return queue(output, args.selection.resolve(), args.ready.resolve(), args.previous_unit)


if __name__ == "__main__":
    sys.exit(main())
