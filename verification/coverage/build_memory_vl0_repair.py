#!/usr/bin/env python3
"""One independent coverage build of the approved segment-VL0 repair."""
import argparse
import os
from pathlib import Path
import sys

import run_vcs_dve_checkpoint as base

ROOT = base.ROOT
REFERENCE = ROOT / "verification/out/repair-closure-coverage-20260927-01"
DISPATCHER = ROOT / "hardware/src/ara_dispatcher.sv"


def compile_command(output):
    command = base.read(REFERENCE / "compile.command.json")["command"]
    replacements = {"buildpath": str(output / "build"), "sim_dir": str(output / "sim")}
    for key in replacements:
        if sum(arg.startswith(key + "=") for arg in command) != 1:
            raise ValueError(f"ambiguous reference compile option: {key}")
    return [f"{arg.split('=', 1)[0]}={replacements[arg.split('=', 1)[0]]}"
            if arg.split("=", 1)[0] in replacements else arg for arg in command]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approved-dispatcher-sha256", required=True)
    args = parser.parse_args()
    output = base.checked_output(args.output)
    base.check_service()
    output.mkdir(parents=True, exist_ok=True)
    state = {"status": "BUILDING", "old_vdb_reuse": False,
             "approved_dispatcher_sha256": args.approved_dispatcher_sha256,
             "unit": os.environ["ARA_CHECKPOINT_UNIT"]}
    try:
        if any((output / p).exists() for p in ("build", "sim", "compile.command.json")):
            raise RuntimeError("refuse build overwrite/retry")
        base.check({str(DISPATCHER): args.approved_dispatcher_sha256})
        reference = base.read(REFERENCE / "sim/vcs_source_manifest.json")
        current = base.collect(Path(reference["filelist"]), ROOT,
                               [Path(p) for p in reference["extra_sources"]])
        live = {r["path"]: r["sha256"] for r in current
                if not Path(r["path"]).is_relative_to(REFERENCE)}
        old = {r["path"]: r["sha256"] for r in reference["files"]}
        base.save(output / "build-source-pins.json", live)
        base.save(output / "build-source-delta.json", {
            "reference": str(REFERENCE), "changed": [p for p, h in live.items()
                                                       if old.get(p) != h]})
        base.save(output / "build-tool-pins.json", base.pins([
            Path(__file__), Path(base.__file__), REFERENCE / "compile.command.json",
            REFERENCE / "sim/vcs_source_manifest.json", REFERENCE / "sim/simulator.conf",
            REFERENCE / "sim/simv.daidir/vcs_rebuild"]))
        base.save(output / "build-status.json", state)
        base.run(compile_command(output), output / "compile.log", 7200)
        base.check(live)
        manifest = base.sources(output / "sim/vcs_source_manifest.json")
        actual = {r["path"]: r["sha256"] for r in manifest["files"]
                  if not Path(r["path"]).is_relative_to(output)}
        if actual != live:
            raise RuntimeError("candidate build did not use the approved source set")
        if base.normalized_vcs(output) != base.normalized_vcs(REFERENCE):
            raise RuntimeError("candidate VCS flags differ beyond independent paths")
        if (output / "sim/simulator.conf").read_bytes() != (REFERENCE / "sim/simulator.conf").read_bytes():
            raise RuntimeError("candidate simulator configuration differs")
        if (output / "build/vcs/bender_script_default").read_bytes() != Path(reference["filelist"]).read_bytes():
            raise RuntimeError("candidate Bender filelist differs")
        base.pure_design(output / "sim/simv.vdb")
        image = base.simulation_image(output / "sim/simv")
        if len(image) < 2 or not (output / "sim/simv.vdb/snps/coverage/db/design/verilog.design.xml").is_file():
            raise RuntimeError("missing runtime libraries or instrumented design")
        base.save(output / "build-image.json", image)
        state.update(status="PASS", image=image, dispatcher_sha256=base.sha256(DISPATCHER))
    except Exception as error:
        state.update(status="FAIL", reason=f"{type(error).__name__}: {error}")
        raise
    finally:
        base.save(output / "build-status.json", state)


if __name__ == "__main__":
    main()
