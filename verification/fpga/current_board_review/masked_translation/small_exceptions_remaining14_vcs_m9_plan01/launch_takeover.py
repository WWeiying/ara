#!/usr/bin/env python3
"""Launch the reviewed, unchanged service envelope once."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "prepared01"
REVIEW = HERE.parent / "small_exceptions_remaining14_review01/entry01.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    envelope = json.loads((OUT / "service_launch.json").read_text())
    for path, digest in envelope["pins"].items():
        if sha(path) != digest:
            raise RuntimeError("Launch input drift: " + path)
    review = json.loads(REVIEW.read_text())
    if not (review["decision"] == "NO_BLOCKER" and review["blockers"] == []
            and review["plan_sha256"] == envelope["plan_sha256"]
            and review["worker_sha256"] == sha(HERE / "replay.py")
            and review["checker_sha256"] == sha(HERE / "checker.py")):
        raise RuntimeError("Concrete entry review mismatch")
    for name in ("launch_command_takeover.json", "launch.json", "complete.json", "replay", "service_exit.json"):
        if (OUT / name).exists():
            raise RuntimeError("Existing launch or execution: " + name)
    env = dict(os.environ, XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}",
               DBUS_SESSION_BUS_ADDRESS=f"unix:path=/run/user/{os.getuid()}/bus")
    unit = "ara-small-exceptions14-m9-01.service"
    query = subprocess.run(["systemctl", "--user", "show", unit, "-p", "LoadState"],
                           env=env, capture_output=True, text=True, timeout=15, check=True)
    if query.stdout.strip() != "LoadState=not-found" or query.stderr.strip():
        raise RuntimeError("Service already exists or cannot be inspected")
    command = [str(REVIEW) if arg == "TESLA_REVIEW" else sha(REVIEW)
               if arg == "TESLA_REVIEW_SHA" else arg for arg in envelope["command_template"]]
    save(OUT / "launch_command_takeover.json", dict(command=command,
         envelope_sha256=sha(OUT / "service_launch.json"), review_sha256=sha(REVIEW),
         started=time.time(), reason="Parent takes over unavailable launching agent"))
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        save(OUT / "systemd_run_takeover.json", dict(observation_timeout=True,
             actual_returncode=None, retry=False, inspect_existing_unit_before_any_next_action=True))
        raise
    save(OUT / "systemd_run_takeover.json", dict(actual_returncode=result.returncode,
         stdout=result.stdout, stderr=result.stderr, completed=time.time(),
         submission_only_not_worker_exit=True))
    print(result.stdout + result.stderr, end="", flush=True)
    if result.returncode:
        raise RuntimeError("Service submission failed; no retry")


if __name__ == "__main__":
    main()
