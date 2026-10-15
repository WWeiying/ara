#!/usr/bin/env python3
"""Bind the actual parent launch and start the independent terminal collector."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKER = HERE.parent / "small_exceptions_remaining14_vcs_m9_plan01"
OUT = WORKER / "prepared01"
REVIEW = HERE.parent / "small_exceptions_remaining14_review01/entry01.json"
UNIT = "ara-small-exceptions14-m9-collector01.service"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    for name in ("binding.json", "launch.json", "result.json", "started.json"):
        if (HERE / name).exists():
            raise RuntimeError("Existing collector artifact: " + name)
    service = json.loads((OUT / "service_exit.json").read_text())
    if tuple(service.get(k) for k in ("EXIT_CODE", "EXIT_STATUS", "SERVICE_RESULT")) != ("exited", "0", "success"):
        raise RuntimeError("Producer did not exit successfully")
    waiter = ROOT / "wait_terminal.py"
    files = [HERE / "audit.py", HERE / "collect.py", Path(__file__).resolve(), waiter,
             WORKER / "launch_takeover.py", OUT / "launch_command_takeover.json",
             OUT / "systemd_run_takeover.json", REVIEW]
    pins = {str(path): sha(path) for path in files}
    env = dict(os.environ, XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}",
               DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{os.getuid()}/bus")
    query = subprocess.run(["systemctl", "--user", "show", UNIT, "-p", "LoadState"],
                           env=env, text=True, capture_output=True, timeout=15, check=True)
    if query.stdout.strip() != "LoadState=not-found" or query.stderr.strip():
        raise RuntimeError("Collector service already exists or query failed")
    save(HERE / "binding.json", dict(review_path=str(REVIEW), review_sha256=sha(REVIEW),
         service_launch_sha256=sha(OUT / "service_launch.json"), waiter_sha256=sha(waiter),
         collector_pins=pins, source="Actual parent takeover receipts; no synthetic worker wait"))
    command = ["systemd-run", "--user", "--collect", "--unit=" + UNIT,
               "--property=RuntimeMaxSec=7200", "--property=KillMode=control-group", "--property=Restart=no",
               "--property=WorkingDirectory=" + str(HERE),
               "--property=StandardOutput=append:" + str(HERE / "service.log"),
               "--property=StandardError=append:" + str(HERE / "service.log"),
               "--property=ExecStopPost=/usr/bin/python3 -B " + str(WORKER / "pinned_service_exit.py") + " " + str(HERE / "service_exit.json"),
               "/usr/bin/python3", "-B", str(HERE / "collect.py")]
    save(HERE / "launch.json", dict(command=command, binding_sha256=sha(HERE / "binding.json"), time=time.time()))
    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=30)
    save(HERE / "launch_receipt.json", dict(actual_submission_returncode=result.returncode,
         stdout=result.stdout, stderr=result.stderr, submission_not_worker_exit=True))
    print(result.stdout + result.stderr, end="", flush=True)
    if result.returncode:
        raise RuntimeError("Collector submission failed; no automatic retry")


if __name__ == "__main__":
    main()
