"""Launch the sealed DC worker only after the active paired VCS worker has finished."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def load(path):
    return json.loads(path.read_bytes())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("out", "branch", "cast"):
        p.add_argument(key, type=Path)
    args = p.parse_args()
    out = args.out.resolve()
    receipts = {}
    plan = load(out / "plan.json")
    hashes = {name: val["new"] for name, val in plan["changes"].items()}
    for name, field, rtl in (
        ("branch", "candidate_ex_stage_sha256", "hardware/deps/cva6/core/ex_stage.sv"),
        ("cast", "candidate_accumulator_sha256", "hardware/src/vlsu/qbs/qbs_fp_accumulator.sv"),
    ):
        path = getattr(args, name).resolve()
        data = path.read_bytes()
        proof = json.loads(data)
        if proof["state"] != "PASS" or proof[field] != hashes[rtl]:
            sys.exit("Independent RTL proof mismatch: " + name)
        receipts[name] = dict(state="PASS", receipt=str(path), sha256=hashlib.sha256(data).hexdigest())

    # The SoC worker holds this file lock from before its first case to after
    # writing its final state. Its process exiting also releases the lock.
    with (out / "worker.lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        state = load(out / "status.json")["state"]
        if state != "WAITING_EXTERNAL_TEST_GATES":
            sys.exit("No paired SoC acceptance; DC not launched. Worker state: " + state)
        if load(out / "soc-pass.json")["candidate_sha256"] != hashes:
            sys.exit("Paired SoC report did not test this candidate")
        gate = out / "timing-authorization.json"
        with gate.open("x") as fd:
            json.dump(dict(authorization="LAUNCH_GLOBAL_DC", candidate_sha256=hashes,
                           **receipts), fd, indent=2)
    subprocess.run([sys.executable, "-B", str(out / "worker.py"), "launch-dc",
                    str(out), "--gate", str(gate)], check=True)


if __name__ == "__main__":
    main()
