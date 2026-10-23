#!/usr/bin/env python3
"""Run one current-runtime twin, or combine two independently completed runs.

Run directly under the owning service. Never builds an image or application.
Reaudit the historical baseline, never rerun it. Functionality PASS is
independent of performance; no deployment approval.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys

from audit_projection_soc_pair import audit
from build_runtime_pack_projection import (APP, BASELINE_SHA256, HERE, read_json,
                                          require_gate, stop, verify_pins)
from run_half_scale_soc import (ROOT, atomic_json, digest, hashes, image_files,
                                run_command, script_files)


def compare(old, new):
    if old["image_pins_sha256"] != new["image_pins_sha256"]:
        raise ValueError("Different simulator images")
    a, b = old["projection"]["result"], new["projection"]["result"]
    for key in ("checksum", "k", "rows", "inputs", "outputs", "tiles", "operations",
                "quantizations", "activation_context", "logical_read_bytes", "timing_scope"):
        if a[key] != b[key]:
            raise ValueError("Different workload/output: " + key)
    phases = {key: dict(before=int(a[key]), after=int(b[key])) for key in
              ("quantize_cycles", "pack_cycles", "matmul_cycles", "timed_cycles")}
    before, after = int(a["timed_cycles"]), int(b["timed_cycles"])
    if min(before, after) <= 0:
        raise ValueError("Invalid cycle measurement")
    return dict(state="PASS", phases=phases,
                performance="improved" if after < before else "regressed" if after > before else "neutral",
                total_cycle_change_percent=100 * (after - before) / before,
                deployment_approved=False)


def verify_build(directory):
    report = read_json(directory / "build.json")
    if report.get("state") != "BUILT_NOT_EXECUTED" or report.get("baseline_sha256") != BASELINE_SHA256:
        raise ValueError("Build is incomplete or baseline differs")
    pins = read_json(directory / "manifest.json")
    artifacts = read_json(directory / "artifacts.json")
    if (digest(directory / "manifest.json") != report["manifest_sha256"] or
            digest(directory / "artifacts.json") != report["artifacts_sha256"]):
        raise ValueError("Build manifest identity differs")
    verify_pins(pins)
    verify_pins(artifacts)
    gate = require_gate(Path(report["native_gate"]))
    if any(pins.get(path) != value for path, value in gate.items()):
        raise ValueError("Build was not gated by this exact native evidence")
    expected = {"baseline": BASELINE_SHA256,
                **{mode: report["modes"][mode]["elf_sha256"] for mode in ("scalar", "vector")}}
    for mode, value in expected.items():
        if digest(directory / mode / APP) != value:
            raise ValueError("Projection executable differs")
    return report, {**pins, **artifacts, **hashes([directory / "build.json", directory / "artifacts.json"])}


def completed_twin(directory, mode, build, required_pins):
    state = read_json(directory / "status.json")
    manifest = directory / "manifest.json"
    pins = read_json(manifest)
    if (state.get("state") != "PASS" or state.get("mode") != mode or
            state.get("child_pid") is not None or
            digest(manifest) != state.get("manifest_sha256")):
        raise ValueError("Twin is incomplete or manifest changed: " + mode)
    verify_pins(pins)
    if any(pins.get(path) != value for path, value in required_pins.items()):
        raise ValueError("Twin used different build/checker/baseline inputs: " + mode)
    result = audit(directory / mode, APP)
    if (result != state.get("cases", {}).get(mode) or
            result["elf_sha256"] != digest(build / mode / APP)):
        raise ValueError("Twin execution identity differs: " + mode)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--baseline-soc", type=Path, required=True,
                   help="Archived original DIRECT run, used to bind ELF and simulator identity")
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--mode", choices=("scalar", "vector"), help="Run only this twin")
    action.add_argument("--combine", nargs=2, type=Path, metavar=("SCALAR_RUN", "VECTOR_RUN"),
                        help="Read-only reaudit of two completed twins; no simulation")
    p.add_argument("--simv", type=Path, help="Required for --mode; must match archived baseline")
    p.add_argument("--tools-root", type=Path, default=Path("/home/wangwy/openproject/ara_dsa"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=2700, help="Per simulation seconds")
    args = p.parse_args()
    if args.timeout < 1:
        p.error("timeout must be positive")
    if args.mode and args.simv is None:
        p.error("--mode requires --simv")
    if args.combine and args.simv is not None:
        p.error("--combine derives the image from the archived baseline")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    build = args.build.resolve(strict=True)
    args.baseline_soc = args.baseline_soc.resolve(strict=True)
    report, pins = verify_build(build)
    historic = audit(args.baseline_soc, APP)
    image = read_json(args.baseline_soc / "image-pins.json")
    simv = (args.simv or Path(image["simv"])).resolve(strict=True)
    if historic["elf_sha256"] != BASELINE_SHA256 or hashes(image_files(simv)) != image["files"]:
        raise ValueError("Not the original baseline ELF/simulator")
    pins.update(hashes([*script_files(), HERE / "audit_projection_soc_pair.py",
                       HERE / "build_runtime_pack_projection.py", HERE / "run_runtime_pack_projection.py",
                       Path(sys.executable).resolve(), *image_files(simv),
                       args.baseline_soc / "status.json", args.baseline_soc / "input-pins.json",
                       args.baseline_soc / "image-pins.json",
                       args.baseline_soc / APP / "work/run.vcs.log",
                       args.baseline_soc / APP / "uvm_result.json",
                       args.baseline_soc / APP / "work/input.elf"]))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / "manifest.json", pins)
    state = dict(state="preparing", pid=os.getpid(), child_pid=None, cases={},
                 mode=args.mode, manifest_sha256=digest(out / "manifest.json"),
                 scope="one real M4/N896/K896 DIRECT row-quantize + pack projection; not fused GGML or whole model",
                 build_sha256=digest(build / "build.json"), historical_baseline=historic,
                 source_provenance=report["source_provenance"],
                 runtime_changes={k: report["modes"][k]["versus_baseline"] for k in ("scalar", "vector")},
                 scalar_vector_sections=report["scalar_vector_sections"], deployment_approved=False)

    def save():
        atomic_json(out / "status.json", state)

    def started(pid):
        state["child_pid"] = pid
        save()

    try:
        if args.combine:
            for mode, directory in zip(("scalar", "vector"), args.combine):
                state["cases"][mode] = completed_twin(directory.resolve(strict=True), mode, build, pins)
            state["consumed_records"] = hashes(path.resolve(strict=True)
                for directory in args.combine
                for path in (directory / "status.json", directory / "manifest.json"))
        else:
            mode = args.mode
            verify_pins(pins)
            verify_build(build)
            state.update(state="running", mode=mode)
            command = [sys.executable, str(HERE / "run_half_scale_soc.py"),
                       "--output", str(out / mode), "--tools-root", str(args.tools_root),
                       "--elf-dir", str(build / mode), "--simv", str(simv),
                       "--cases", APP, "--l2-mb", "16", "--timeout", str(args.timeout)]
            state["command"] = command
            save()
            try:
                rc = run_command(command, out / (mode + ".log"), args.timeout + 300,
                                 os.environ.copy(), started)
            finally:
                state["child_pid"] = None
                save()
            if rc != 0 or read_json(out / mode / "status.json").get("state") != "PASS":
                raise RuntimeError(f"Projection worker failed: {mode}, returncode={rc}")
            result = audit(out / mode, APP)
            if result["elf_sha256"] != digest(build / mode / APP):
                raise ValueError("Executed wrong executable")
            compare(historic, result)
            state["cases"][mode] = result
            verify_pins(pins)
            save()
        verify_build(build)
        verify_pins(pins)
        if audit(args.baseline_soc, APP) != historic:
            raise ValueError("Historical baseline evidence drifted")
        cases = state["cases"]
        comparisons = {"baseline_to_current_" + mode: compare(historic, result)
                       for mode, result in cases.items()}
        if args.combine:
            verify_pins(state["consumed_records"])
            for mode, directory in zip(("scalar", "vector"), args.combine):
                if completed_twin(directory.resolve(strict=True), mode, build, pins) != cases[mode]:
                    raise ValueError("Completed twin evidence drifted")
            comparisons["current_scalar_to_vector"] = compare(cases["scalar"], cases["vector"])
        state.update(state="PASS", comparisons=comparisons,
                     non_pack_twin_sections_identical=not report["scalar_vector_sections"]["non_pack_sections"])
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()
    print(json.dumps(state["comparisons"], sort_keys=True))


if __name__ == "__main__":
    main()
