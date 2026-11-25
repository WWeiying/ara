"""Replay the previous candidate's sealed seven ELF tests, replacing two RTL files."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import subprocess

from run_operand_ext import ROOT, read, save, sha, verify
from run_request_lane_timing_soc import CASES, TIMERS

CHANGED = ("hardware/src/common_cells_compat/fall_through_register_v1.sv",
           "hardware/src/vlsu/qbs/qbs_block_adapter.sv")


def replay(previous, out):
    verify(previous)
    prior = read(previous / "status.json")
    if prior["state"] != "PASS":
        raise ValueError("reference has not passed")
    files = (previous / "candidate.f").read_text()
    hashes = {}
    for rel in CHANGED:
        orig, copy = previous / "source" / rel, out / rel
        if files.splitlines().count(str(orig)) != 1:
            raise ValueError(f"missing or duplicated active RTL: {orig}")
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, copy)
        hashes[rel] = sha(copy)
        files = files.replace(str(orig), str(copy))
    flist = out / "candidate.f"
    flist.write_text(files)
    argv = read(previous / "candidate/command.json")
    argv[argv.index("-f") + 1] = str(flist)
    save(out / "command.json", argv)
    save(out / "status.json", {"state": "BUILDING", "changed_sha256": hashes})
    with (out / "build.log").open("w") as log:
        subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)

    def case(name):
        d = out / name
        d.mkdir()
        argv = read(previous / "candidate" / name / "command.json")
        argv[0] = str(out / "simv")
        with (d / "run.log").open("w") as log:
            subprocess.run(argv, cwd=d, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
        log = (d / "run.log").read_text(errors="replace")
        if ("*** SUCCESS ***" not in log or (CASES[name] and CASES[name] not in log) or
                re.search(r"Fatal:|Error:|\*\*\* FAILED \*\*\*", log)):
            raise ValueError(f"failed functional check: {name}")
        metrics = {k: list(map(int, re.findall(pattern, log))) for k, pattern in TIMERS}
        if metrics != prior["measured"]["candidate"][name]:
            raise ValueError(f"timing changed: {name}: {metrics}")
        return name, metrics

    save(out / "status.json", {"state": "RUNNING", "changed_sha256": hashes})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(case, CASES))
    verify(previous)
    if any(sha(out / rel) != h for rel, h in hashes.items()):
        raise ValueError("candidate drift")
    save(out / "status.json", {"state": "PASS", "changed_sha256": hashes, "equal_cycles": results,
                               "reference": str(previous), "image_sha256": sha(out / "simv")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("previous", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    out = args.out.resolve()
    if any(out.iterdir()):
        raise ValueError("requires empty output directory")
    try:
        replay(args.previous.resolve(), out)
    except Exception as exc:
        save(out / "status.json", {"state": "FAIL", "error": str(exc)})
        raise
