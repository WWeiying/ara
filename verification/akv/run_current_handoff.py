#!/usr/bin/env python3
"""Build current RTL and check RVV/QBS/AKV handoff in a fresh directory.

Run in a detached session. This is VCS functional verification, not synthesis.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sources():
    names = subprocess.check_output([
        "git", "ls-files", "-z", "hardware/src", "hardware/include", "hardware/tb",
        "hardware/Makefile", "config", "Bender.yml", "Bender.lock", "apps/Makefile",
        "apps/common", "apps/qbs_akv_handoff_smoke", "verification/akv/run_qbs_akv_handoff.sh",
    ], cwd=ROOT).decode().split("\0")
    return {name: sha(ROOT / name) for name in names if name and (ROOT / name).is_file()}


def run(argv, log, timeout, env=None):
    with log.open("w") as stream:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True, env=env)
        try:
            rc = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if rc:
        raise RuntimeError(f"command failed ({rc}); see {log}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    sim_relative = (out / "sim").relative_to(ROOT / "hardware")
    out.mkdir(parents=True, exist_ok=False)
    state = {"status": "RUNNING", "phase": "compile", "pid": os.getpid(),
             "started_at": datetime.now(timezone.utc).isoformat(),
             "revision": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                 cwd=ROOT, text=True).strip(),
             "source_sha256": sources(),
             "scope": "current RTL; 4 lanes; VLEN=1024; 1 MiB simulated L2; QBS and AKV-v2"}

    def save():
        temporary = out / "status.json.tmp"
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(out / "status.json")

    save()
    try:
        (out / "source.patch").write_bytes(subprocess.check_output(
            ["git", "diff", "HEAD", "--", "hardware", "apps", "config", "verification"], cwd=ROOT))
        run(["make", "-C", str(ROOT / "hardware"), "compile", "config=default", "qbs=1",
             "akv_v2=1", "sim_l2_mb=1", "fail_on_assert=1", f"sim_dir={sim_relative}",
             f"buildpath={out / 'build'}"], out / "compile.log", 1800)
        if sources() != state["source_sha256"]:
            raise RuntimeError("sources changed during compilation; refusing a mixed build")
        state.update(phase="handoff", simv_sha256=sha(out / "sim/simv"),
                     simulator_config_sha256=sha(out / "sim/simulator.conf"))
        save()
        env = dict(os.environ, QBS_AKV_SIMV=str(out / "sim/simv"), QBS_AKV_SIM_L2_MB="1",
                   QBS_AKV_TIMEOUT="600", QBS_AKV_RUN_ROOT=str(out / "handoff"))
        run([str(ROOT / "verification/akv/run_qbs_akv_handoff.sh")], out / "handoff.log", 900, env)
        if sources() != state["source_sha256"]:
            raise RuntimeError("sources changed during handoff; review saved evidence")
        state.update(status="PASS", phase="complete")
    except Exception as error:
        state.update(status="FAIL", error=str(error))
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    print(f"{state['status']}: {out}")
    return 0 if state["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
