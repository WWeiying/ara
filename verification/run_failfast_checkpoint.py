#!/usr/bin/env python3
"""Run a frozen JSON list of {name, command: argv-list, cwd: absolute-path}.

Production use MUST run inside ONE systemd --user service with
KillMode=control-group and Restart=no (not a scope or RemainAfterExit=yes). This may be the main
process, or its Python driver MUST exit immediately and nonzero when this
supervisor returns nonzero. No next stage may start after that failure.
Use a unique service name and a bounded TimeoutStopSec, for example:

  systemd-run --user --unit=ara-checkpoint-UNIQUE --service-type=exec \
    -p KillMode=control-group -p Restart=no -p TimeoutStopSec=5s \
    --working-directory=/absolute/worktree /usr/bin/python3 \
    /absolute/worktree/verification/run_failfast_checkpoint.py \
    --plan /absolute/plan.json --jobs 5 --output /absolute/NEW_DIRECTORY

Each direct child gets a private process group. Runners that create additional
sessions escape that group; only the service cgroup guarantees their cleanup
when the service main process exits. Do not treat standalone execution as that guarantee.
Commands must return nonzero for every non-PASS verdict, including audit failures.
Exit zero is the ONLY success signal interpreted here; no test logs are parsed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def load_plan(path: Path) -> tuple[bytes, list[dict]]:
    raw = path.read_bytes()
    plan = json.loads(raw)
    if not isinstance(plan, list) or not plan:
        raise ValueError("plan must be a nonempty JSON list")
    names = set()
    for item in plan:
        if not isinstance(item, dict) or set(item) != {"name", "command", "cwd"}:
            raise ValueError("each job requires exactly name, command, cwd")
        name, command, cwd = item["name"], item["command"], item["cwd"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("job names must be unique nonempty strings")
        names.add(name)
        if (not isinstance(command, list) or not command or
                not all(isinstance(arg, str) and "\0" not in arg for arg in command) or
                not command[0]):
            raise ValueError(f"{name}: command must be a nonempty argv list")
        if (not isinstance(cwd, str) or not Path(cwd).is_absolute() or
                not Path(cwd).is_dir()):
            raise ValueError(f"{name}: cwd must be an existing absolute directory")
    return raw, plan


def process_state(pid: int) -> dict[str, str]:
    try:
        fields = {}
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("State", "PPid", "NSpgid", "NSsid"):
                fields[key] = value.strip()
        return fields
    except FileNotFoundError:
        return {"State": "absent"}
    except OSError as error:
        return {"observation_error": str(error)}


def stop_groups(active: dict[int, subprocess.Popen]) -> dict:
    children = {index: {"index": index, "pid": process.pid, "signal_errors": [],
                        "before": process_state(process.pid)}
                for index, process in active.items()}

    def send(sig: int) -> None:
        for index, process in active.items():
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            except OSError as error:
                children[index]["signal_errors"].append(f"{sig.name}: {error}")

    send(signal.SIGTERM)
    # Bound cleanup even when a child ignores TERM or a runner waits on workers.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if all(process.poll() is not None for process in active.values()):
            break
        time.sleep(0.02)
    send(signal.SIGKILL)
    # wait() is the ownership proof for direct children, not kill(pid, 0).
    # Use one bounded deadline for the whole batch, and never discard a timeout.
    deadline = time.monotonic() + 3.0
    for index, process in active.items():
        try:
            rc = process.wait(timeout=max(0.0, deadline - time.monotonic()))
            children[index].update(reaped=True, returncode=rc)
        except subprocess.TimeoutExpired:
            children[index].update(reaped=False, returncode=None,
                                   reason="SIGKILL sent; child exit/reaping deadline exceeded")
        children[index]["after"] = process_state(process.pid)
    return {"status": "DIRECT_CHILDREN_REAPED" if all(
                item["reaped"] for item in children.values()) else "INCOMPLETE",
            "children": list(children.values()),
            "nested_sessions": "requires service cgroup cleanup after driver exits"}


def run(plan_path: Path, output: Path, jobs: int = 5) -> int:
    if not 1 <= jobs <= 5:
        raise ValueError("jobs must be between 1 and 5")
    raw, plan = load_plan(plan_path)
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_bytes(raw)
    logs = output / "logs"
    logs.mkdir()
    records = [{**item, "status": "PENDING", "returncode": None,
                "stdout": str(logs / f"{index:04d}.log")}
               for index, item in enumerate(plan)]
    state = {"status": "RUNNING", "started_at": timestamp(), "jobs": jobs,
             "plan_source": str(plan_path.absolute()), "results": records,
             "systemd_invocation_id": os.environ.get("INVOCATION_ID"),
             "nested_cleanup_requires_systemd_control_group": True}
    active: dict[int, subprocess.Popen] = {}
    cancelled_signal = None

    def cancel(signum, _frame):
        nonlocal cancelled_signal
        cancelled_signal = signum

    def publish() -> None:
        atomic_json(output / "status.json", state)

    def observe() -> tuple[int | None, bool]:
        finished = [(index, process.poll()) for index, process in active.items()]
        failure = None
        changed = False
        for index, rc in finished:
            if rc is None:
                continue
            changed = True
            records[index].update(status="PASS" if rc == 0 else "FAIL",
                                  returncode=rc, finished_at=timestamp())
            if rc != 0 and failure is None:
                failure = index
        # Keep failed groups available for cleanup, even after their leader exits.
        if failure is None:
            for index, rc in finished:
                if rc is not None:
                    del active[index]
        return failure, changed

    previous = {sig: signal.signal(sig, cancel) for sig in (signal.SIGINT, signal.SIGTERM)}
    failure = None
    error = None
    next_index = 0
    try:
        publish()
        while next_index < len(plan) or active:
            failure, changed = observe()
            if failure is not None or cancelled_signal is not None:
                break
            if next_index < len(plan) and len(active) < jobs:
                index = next_index
                record = records[index]
                try:
                    with Path(record["stdout"]).open("wb") as log:
                        active[index] = subprocess.Popen(
                            record["command"], cwd=record["cwd"], stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                        )
                except OSError as exc:
                    record.update(status="ERROR", reason=str(exc), finished_at=timestamp())
                    failure = index
                    break
                record.update(status="RUNNING", pid=active[index].pid, started_at=timestamp())
                next_index += 1
                publish()
                continue
            if changed:
                publish()
            if active:
                time.sleep(0.05)
        if failure is None and cancelled_signal is None:
            state.update(status="PASS", finished_at=timestamp())
            publish()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            if failure is not None or cancelled_signal is not None or error is not None:
                state.update(status="CANCELLED" if cancelled_signal is not None else "FAIL",
                             finished_at=timestamp())
                stop = {"status": state["status"], "observed_at": timestamp(),
                        "failure": dict(records[failure]) if failure is not None else None,
                        "signal": cancelled_signal, "error": error, "cleanup": {"status": "PENDING"}}
                for record in records:
                    if record["status"] == "PENDING":
                        record.update(status="CANCELLED", reason="checkpoint stopped",
                                      finished_at=timestamp())
                    elif record["status"] == "RUNNING":
                        record.update(status="STOPPING", reason="checkpoint stopped")
                try:
                    atomic_json(output / "STOP.json", stop)
                    publish()
                finally:
                    cleanup = stop_groups(active)
                    stop["cleanup"] = cleanup
                    state["cleanup"] = cleanup
                    for child in cleanup["children"]:
                        record = records[child["index"]]
                        record["termination"] = child
                        if record["status"] == "STOPPING":
                            record.update(status="CANCELLED" if child["reaped"] else "TERMINATION_PENDING",
                                          finished_at=timestamp())
                    atomic_json(output / "STOP.json", stop)
                    publish()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return 0 if state["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.plan, args.output, args.jobs)
    except (OSError, ValueError) as exc:
        print(f"checkpoint error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
