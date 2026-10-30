#!/usr/bin/env python3
"""Run an existing SoC image on a sealed fused-M4 ABBA preparation benchmark."""
import argparse
import json
import os
from pathlib import Path
import re

from run_half_scale_soc import ROOT, atomic_json, digest, hashes, image_files, script_files
from run_tile_context_engine import run_command


def check_result(text):
    records = re.findall(r"^M4_SOC trial=(\d+) path=(generic|vector) cycles=(\d+) flags=(\d+) used=(\d+)\s*$",
                         text, re.M)
    if len(records) != 4:
        raise ValueError("Missing or duplicate trial records")
    result = []
    for index, (trial, path, cycles, flags, used) in enumerate(records):
        expected = "vector" if index in (1, 2) else "generic"
        if int(trial) != index or path != expected or int(used) != int(expected == "vector") or int(cycles) <= 0:
            raise ValueError("Unexpected ABBA sequence")
        result.append(dict(trial=index, path=path, cycles=int(cycles), fcsr=int(flags)))
    if len({r["fcsr"] for r in result}) != 1:
        raise ValueError("FP state mismatch")
    summary = re.findall(r"^M4_SOC_RESULT errors=(\d+) bytes=(\d+) inputs=3584 k=896 calls=4 golden=linux_ggml\s*$",
                         text, re.M)
    if summary != [("0", "3808")]:
        raise ValueError("Golden or data/environment check failed")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--simv", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=2700)
    args = p.parse_args()
    build, simv = args.build.resolve(strict=True), args.simv.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state="preflight", pid=os.getpid(), child_pid=None)

    def save():
        atomic_json(out / "status.json", state)

    save()
    try:
        report = json.loads((build / "build.json").read_text())
        elf = build / "qbs_m4_prepare_soc"
        source_pins = json.loads((build / "manifest.json").read_text())
        if hashes(map(Path, source_pins)) != source_pins or digest(elf) != report["elf_sha256"]:
            raise ValueError("Build input or executable drift")
        pins = hashes([*image_files(simv), *script_files(), Path(__file__),
                       ROOT / "verification/qbs/run_half_scale_soc.py",
                       ROOT / "verification/qbs/run_tile_context_engine.py", elf,
                       build / "build.json", build / "manifest.json", *map(Path, source_pins)])
        atomic_json(out / "manifest.json", pins)
        env = os.environ.copy()
        env["ARA_VCS_TIMEOUT_SECONDS"] = str(args.timeout)
        command = ["bash", str(ROOT / "verification/uvm/run_real_dut_case.sh"), str(simv),
                   str(elf), "qbs_m4_prepare_soc", str(out / "soc")]

        def started(pid):
            state.update(state="running", child_pid=pid, command=command)
            save()

        rc = run_command(command, out / "worker.log", args.timeout + 120, env, started)
        state["child_pid"] = None
        if rc:
            raise RuntimeError(f"VCS/checker returned {rc}; preserve worker.log")
        log = out / "soc/work/run.vcs.log"
        trials = check_result(log.read_text())
        if hashes(map(Path, pins)) != pins:
            raise ValueError("Pinned sources changed during execution")
        generic = sum(t["cycles"] for t in trials if t["path"] == "generic")
        vector = sum(t["cycles"] for t in trials if t["path"] == "vector")
        atomic_json(out / "result.json", dict(state="PASS", trials=trials,
                    generic_sum_cycles=generic, vector_sum_cycles=vector,
                    preparation_speedup=generic / vector, log_sha256=digest(log),
                    scope="Two ABBA observations per path; preparation only, not projection/model speedup"))
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
