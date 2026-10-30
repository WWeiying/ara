#!/usr/bin/env python3
"""Test actual QBS commit -> modeled VRF -> seed mapper -> accumulator."""
import argparse
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import ROOT, atomic_json, hashes
from run_seed_restore import prototype
from run_tile_context_engine import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    directory = ROOT / "verification/qbs"
    query = ["make", "-s", "--no-print-directory", "-C", str(directory),
             "--eval=print-seed-sources:;@printf '%s\\n' $(RTL_SOURCES)", "print-seed-sources"]
    sources = [Path(line) for line in subprocess.check_output(query, text=True).splitlines()]
    mapper = ROOT / "hardware/src/vlsu/qbs/qbs_vrf_seed_mapper.sv"
    bench = directory / "qbs_vrf_seed_mapper_tb.sv"
    seed_source = ROOT / "hardware/src/vlsu/qbs/qbs_fp_accumulator.sv"
    candidate = out / "qbs_fp_accumulator_seeded.sv"
    candidate.write_text(prototype(seed_source.read_text()))
    pins = hashes([*sources, mapper, bench, seed_source, candidate, Path(__file__),
                   directory / "run_seed_restore.py", directory / "run_half_scale_soc.py",
                   directory / "run_tile_context_engine.py", directory / "Makefile",
                   *ROOT.glob("hardware/deps/common_cells/include/**/*.svh"),
                   *ROOT.glob("hardware/deps/axi/include/**/*.svh")])
    atomic_json(out / "manifest.json", pins)
    state = dict(state="BUILDING", pid=os.getpid(), child_pid=None)
    def save():
        atomic_json(out / "status.json", state)
    def started(pid):
        state["child_pid"] = pid
        save()
    save()
    try:
        command = ["vcs", "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
                   "+incdir+" + str(ROOT / "hardware/deps/common_cells/include"),
                   "+incdir+" + str(ROOT / "hardware/deps/axi/include"), *map(str, sources),
                   str(candidate), str(mapper), str(bench), "-top", "qbs_vrf_seed_mapper_tb",
                   "-o", str(out / "simv")]
        atomic_json(out / "build-command.json", command)
        if run_command(command, out / "compile.log", 300, os.environ.copy(), started):
            raise RuntimeError("VRF seed mapper compile failed")
        state["state"] = "RUNNING"
        save()
        if run_command([str(out / "simv"), "-l", str(out / "run.log")],
                       out / "console.log", 120, os.environ.copy(), started):
            raise RuntimeError("VRF seed mapper failed")
        log = (out / "run.log").read_text()
        matches = re.findall(r"^QBS_VRF_SEED_PASS cases=961 checks=(\d+) reset_flush=1$", log, re.M)
        if (len(matches) != 1 or int(matches[0]) < 100000 or
                re.search(r"Fatal:|Error:", log) or hashes(map(Path, pins)) != pins):
            raise ValueError("Incomplete VRF roundtrip or source drift")
        state["state"] = "PASS"
        atomic_json(out / "result.json", dict(state="PASS", cases=961, checks=int(matches[0]),
            shape_count=192, scenarios_per_shape=5, reset_flush=1,
            scope="Actual commit and accumulator; modeled VRF/StA, not lane/ISA/SoC integration",
            evidence_sha256=hashes([out / "run.log", out / "manifest.json", candidate])))
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__":
    main()
