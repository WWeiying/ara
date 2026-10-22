#!/usr/bin/env python3
"""Fresh-image segment-VL0 repair: one serial gate, eight-worker fail-fast, DVE."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import sys

import run_vcs_dve_checkpoint as base
import run_repair_closure_coverage as repair
import build_memory_vl0_repair as build

ROOT, HERE = base.ROOT, base.HERE
SCRIPT = Path(__file__).resolve()
FOCUSED = "vmemory_gap_nf5_e8_indexed"
CONTROLS = ("vle8", "vse8", "vl1r", "vs1r", "vsegment_emul_edges",
            "vindexed_vstart_edges", "vunit_vstart_edges", "vlseg", "vsetvl", "vadd")
SELECTION = ROOT / "verification/tests/rvv_memory_gap_selection.json"
read, save, check, pins = base.read, base.save, base.check, base.pins
require = repair.require


def prepare(output):
    require(not (output / "plan.json").exists(), "plan already exists; no overwrite")
    check(read(output / "build-source-pins.json"))
    names = read(SELECTION)["tests"]
    require(len(names) == len(set(names)) == 40, "expected exact 40 memory cases")
    require(all(n.startswith("rvv:vmemory_gap_") for n in names), "non-memory selection")
    focus = "rvv:" + FOCUSED
    require(focus in names, "focused regression missing")
    names = [focus] + [n for n in names if n != focus] + ["rvv:" + n for n in CONTROLS]
    jobs, files = {}, dict(read(output / "build-source-pins.json"))
    (output / "inputs").mkdir(exist_ok=False)
    for test in names:
        name = test.split(":", 1)[1]
        original = ROOT / "apps/bin" / ("rv64uv-ara-" + name)
        source = ROOT / "apps/riscv-tests/isa/rv64uv" / (name + ".c")
        target = output / "inputs" / (name + ".elf")
        shutil.copyfile(original, target)
        files.update(pins([original, source, target]))
        jobs[name] = {"name": name, "kind": "directed", "test": test,
                      "elf": str(target), "elf_sha256": base.sha256(target),
                      "coverage_test": name, "timeout_s": 300,
                      "replacement": False, "fault_vstart_probe": False}
    old = read(build.REFERENCE / "plan.json")["jobs"]["axpy"]
    axpy = Path(old["elf"])
    require(axpy.is_file(), "expected available frozen AXPY control")
    check({str(axpy): old["elf_sha256"]})
    target = output / "inputs/axpy.elf"
    shutil.copyfile(axpy, target)
    jobs["axpy"] = dict(old, elf=str(target), timeout_s=300)
    files.update(pins([axpy, target, build.REFERENCE / "plan.json", SELECTION,
                      ROOT / "apps/riscv-tests/isa/rv64uv/vmemory_gap_body.h",
                      ROOT / "verification/tests/generate_rvv_memory_gaps.py",
                      ROOT / "verification/tests/build_rvv_memory_gaps.py",
                      output / "build-source-pins.json", output / "build-tool-pins.json",
                      Path(build.__file__), SCRIPT]))
    files.update(read(output / "build-tool-pins.json"))
    files.update(pins(repair.tool_paths()))
    files.update(pins([HERE / "prepare_dve_waivers.py", HERE / "dve_waivers.tcl"]))
    plan = {"jobs": jobs, "files": files, "workers": 8, "focused": FOCUSED,
            "old_vdb_reuse": False, "policy": "STOP_ON_ANY_NON_PASS",
            "metrics": base.METRICS, "memory_cases": 40, "controls": list(CONTROLS) + ["axpy"]}
    save(output / "plan.json", plan)
    save(output / "plan.sha256.json", pins([output / "plan.json"]))
    frozen(output)
    save(output / "status.json", {"status": "PREPARED", "total": len(jobs),
                                  "simulations_started": False, "old_vdb_reuse": False})
    print(f"PREPARED {len(jobs)} cases; focused={FOCUSED}; no simulations started", flush=True)


def frozen(output, runtime=False):
    check(read(output / "plan.sha256.json"))
    plan = read(output / "plan.json")
    check(plan["files"])
    if runtime:
        check(read(output / "runtime.sha256.json"))
        record = read(output / "runtime.json")
        check(record["files"])
        require(base.simulation_image(output / "sim/simv") == record["image"], "image inventory drift")
        require(base.simulation_image(output / "inputs/coverage_simv") == record["wrapper_image"],
                "wrapper image drift")
        base.sources(output / "sim/vcs_source_manifest.json")
    return plan


def runtime(output):
    require(read(output / "build-status.json")["status"] == "PASS", "independent build not PASS")
    check(read(output / "build-image.json"))
    check(read(output / "build-source-pins.json"))
    base.sources(output / "sim/vcs_source_manifest.json")
    image = base.simulation_image(output / "sim/simv")
    require(image == read(output / "build-image.json"), "built image inventory drift")
    base.pure_design(output / "sim/simv.vdb")
    wrapper = output / "inputs/coverage_simv"
    shutil.copyfile(HERE / "vcs_coverage_exec.py", wrapper)
    wrapper.chmod(0o755)
    Path(str(wrapper) + ".daidir").symlink_to(output / "sim/simv.daidir", target_is_directory=True)
    shutil.copyfile(output / "sim/simulator.conf", output / "inputs/simulator.conf")
    save(output / "inputs/coverage-wrapper.json", {"simv": str(output / "sim/simv"),
         "image": image, "results": str(output / "results")})
    wrapper_image = base.simulation_image(wrapper)
    save(output / "candidate.json", {"image": wrapper_image, "real_image": image})
    paths = [output / p for p in ("candidate.json", "build-status.json", "compile.command.json",
             "sim/vcs_source_manifest.json", "sim/simulator.conf", "sim/simv.daidir/vcs_rebuild",
             "inputs/coverage_simv", "inputs/coverage-wrapper.json", "inputs/simulator.conf")]
    record = {"image": image, "wrapper_image": wrapper_image, "files": dict(pins(paths), **image),
              "design_files": base.inventory(output / "sim/simv.vdb")}
    save(output / "runtime.json", record)
    save(output / "runtime.sha256.json", pins([output / "runtime.json"]))
    return record


def merge(output, plan, record):
    outcomes = [read(output / "outcomes" / (name + ".json")) for name in plan["jobs"]]
    databases = {str(output / "sim/simv.vdb"): record["design_files"]}
    base.pure_design(output / "sim/simv.vdb")
    for name, item in zip(plan["jobs"], outcomes):
        require(item["name"] == name and item["status"] == "PASS" and item["admitted"],
                "DVE requires independent PASS evidence")
        require(item["elf_sha256"] == plan["jobs"][name]["elf_sha256"] and
                item["coverage_test"] == plan["jobs"][name]["coverage_test"], "coverage identity differs")
        vdb = Path(item["vdb"]).resolve()
        require(vdb.is_relative_to(output / "results" / name) and vdb.name == "code.vdb" and
                str(vdb) not in databases, "old/foreign/duplicate VDB rejected")
        check(item["files"])
        require(repair.coverage.valid_vdb(vdb, item["coverage_test"], str(output / "sim/simv")) ==
                item["vdb_files"], "VDB changed")
        databases[str(vdb)] = item["vdb_files"]
    require(all(base.inventory(Path(p)) == hashes for p, hashes in databases.items()), "VDB drift")
    save(output / "dve-inputs.before.json", databases)
    inputs = output / "dve-inputs.txt"
    inputs.write_text("\n".join(databases) + "\n")
    target = output / "dve"
    require(repair.coverage.invoke(["bash", str(repair.DVE / "run_dve_coverage.sh"), str(target),
            "--inputs-file", str(inputs)], output / "logs/dve.log", 720,
            {"DVE_COVERAGE_TIMEOUT": "600", "DVE_WAIVERS": "auto"}) == 0, "DVE export failed")
    expected = [str(Path(o["vdb"]).with_suffix("") / o["coverage_test"]) for o in outcomes]
    require((target / "selected_tests.txt").read_text().splitlines() == expected, "DVE selection mismatch")
    after = {p: base.inventory(Path(p)) for p in databases}
    save(output / "dve-inputs.after.json", after)
    require(after == databases, "DVE modified source databases")
    save(output / "collection.json", {"status": "PASS", "passed": len(outcomes), "total": len(outcomes),
         "scope": "NEW_REPAIRED_IMAGE_INDEPENDENT_PASS_ONLY", "old_vdb_reuse": False,
         "image": record["image"], "cases": outcomes, "metrics": base.METRICS,
         "reports": base.inventory(target)})


def execute(output, build_unit):
    base.check_service()
    state = read(output / "status.json")
    require(state["status"] == "PREPARED", "only fresh PREPARED output may execute")
    try:
        state.update(status="RUNNING", phase="waiting-independent-build", build_unit=build_unit)
        save(output / "status.json", state)
        # Existing bounded service-wait API; never starts or rebuilds an image.
        repair.wait_build(build_unit, output, 7200, adopt_built=True)
        with (ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan = frozen(output)
            record = runtime(output)
            frozen(output, True)
            (output / "logs").mkdir(exist_ok=True)
            state.update(phase="focused-nf5-e8-indexed", simulations_started=True)
            save(output / "status.json", state)
            repair.schedule(output, [FOCUSED], 1)
            (output / "scheduler").rename(output / "focused-scheduler")
            state.update(phase="regression-eight-workers")
            save(output / "status.json", state)
            repair.schedule(output, [n for n in plan["jobs"] if n != FOCUSED], 8)
            frozen(output, True)
            state.update(phase="PASS-only-DVE")
            save(output / "status.json", state)
            merge(output, plan, record)
            frozen(output, True)
            state.update(status="PASS", phase="complete", passed=len(plan["jobs"]))
            save(output / "status.json", state)
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}", verified_coverage=False)
        save(output / "status.json", state)
        raise


# Reuse the repair runner's worker, directed runner, audits, and fail-fast scheduler.
# Only routing and source-freeze policy differ; no existing module is edited.
repair.SCRIPT = SCRIPT
repair.frozen = frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--worker")
    modes.add_argument("--directed")
    parser.add_argument("--build-unit")
    args = parser.parse_args()
    output = base.checked_output(args.output)
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    if args.worker:
        return repair.worker(output, args.worker)
    if args.directed:
        repair.directed(output, args.directed)
    elif args.execute:
        require(bool(args.build_unit), "independent build unit required")
        execute(output, args.build_unit)
    else:
        prepare(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
