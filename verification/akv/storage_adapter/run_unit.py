#!/usr/bin/env python3
"""Independent bounded host-VCS test of the experimental legacy write adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

HERE = Path(__file__).resolve().parent
# 8 alignments for each row length, seven abort/recovery rows and one final row.
EXPECTED_BYTES = 8 * (128 + 192 + 256) + 7 * 256 + 128 + 2 * 128
EXPECTED_WRITES = EXPECTED_BYTES // 16


def hashes(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(command, out, name, limit):
    save(out / (name + ".command.json"), command)
    with (out / (name + ".log")).open("w") as log:
        child = subprocess.Popen(command, cwd=out, stdout=log, stderr=log,
                                 start_new_session=True)
        try:
            return child.wait(timeout=limit)
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("Host VCS unavailable")
    sources = [HERE / "akv_legacy_repacker.sv", HERE / "repacker_tb.sv"]
    pins = hashes([*sources, Path(__file__).resolve(), Path(vcs), Path(vcs).resolve()])
    save(out / "source-pins.json", pins)
    save(out / "status.json", {"state": "BUILDING"})
    try:
        code = run([vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                    *map(str, sources), "-top", "repacker_tb", "-o", str(out / "simv")],
                   out, "compile", 300)
        if code:
            raise RuntimeError("VCS compilation failed")
        save(out / "status.json", {"state": "RUNNING"})
        code = run([str(out / "simv")], out, "positive", 60)
        text = (out / "positive.log").read_text()
        match = re.findall(rf"^REPACK_UNIT_PASS rows=34 aborts=8 writes={EXPECTED_WRITES} "
                           rf"bytes={EXPECTED_BYTES} latency_checks=34$", text, re.M)
        if code or len(match) != 1 or re.search(r"Fatal:|Error:|REPACK_TIMEOUT", text):
            raise RuntimeError("Repacker RTL test did not pass; inspect positive.log")
        if hashes(map(Path, pins)) != pins:
            raise RuntimeError("Input identity changed")
        save(out / "result.json", {
            "state": "PASS", "rows": 34, "aborts": 8, "latency_checks": 34,
            "writes": EXPECTED_WRITES, "checked_bytes": EXPECTED_BYTES,
            "production_integrated": False, "ppa_measured": False,
            "evidence": hashes([out / "source-pins.json", out / "positive.log",
                                out / "compile.log", out / "simv"])})
        save(out / "status.json", {"state": "PASS"})
    except BaseException as exc:
        save(out / "status.json", {"state": "FAIL", "error": repr(exc)})
        raise


if __name__ == "__main__":
    main()
