#!/usr/bin/env python3
"""Run an immutable QBS engine binary against command and real-capture tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    out, simv = args.output.resolve(), args.simv.resolve()
    if not simv.is_file():
        parser.error(f"missing compiled simulator: {simv}")
    if not args.worker:
        out.mkdir(parents=True, exist_ok=False)
        with (out / "driver.log").open("w") as log:
            child = subprocess.Popen([
                sys.executable, str(Path(__file__).resolve()), "--worker",
                "--output", str(out), "--simv", str(simv)], cwd=out,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
        print(f"started pid={child.pid} output={out}")
        return
    state = {"state": "RUNNING", "pid": os.getpid(), "simv": str(simv),
             "simv_sha256": hashlib.sha256(simv.read_bytes()).hexdigest(),
             "started": datetime.now(timezone.utc).isoformat()}
    status = out / "status.json"
    status.write_text(json.dumps(state, indent=2) + "\n")
    try:
        vectors = out / "commands.vectors"
        subprocess.run([str(ROOT / "verification/qbs/qbs_command_vectors"),
                        str(vectors)], check=True, cwd=out)
        log = out / "commands.log"
        subprocess.run([str(simv), "-l", str(log),
                        f"+QBS_COMMAND_VECTOR_FILE={vectors}"],
                       check=True, cwd=out, timeout=600)
        text = log.read_text()
        if "QBS engine PASS:" not in text or "Fatal:" in text:
            raise RuntimeError("command/fault tests did not report PASS")
        env = dict(os.environ, QBS_ADAPTIVE_RTL_SIMV=str(simv),
                   QBS_ADAPTIVE_RTL_RESULT_DIR=str(out / "real"))
        subprocess.run([str(ROOT / "verification/qbs/run_adaptive_real_rtl.sh")],
                       check=True, cwd=out, env=env, timeout=1800)
        state["state"] = "PASS"
    except Exception as exc:
        state.update(state="FAIL", error=str(exc))
    state["finished"] = datetime.now(timezone.utc).isoformat()
    status.write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    main()
