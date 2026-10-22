#!/usr/bin/env python3
"""Show registered verification results without starting or stopping jobs."""
import argparse
from collections import Counter, deque
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def service_state(unit):
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, "-p", "ActiveState",
             "-p", "SubState", "-p", "MainPID", "-p", "Result"],
            capture_output=True, text=True, timeout=5)
        if result.returncode:
            return {}
        return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    except (OSError, subprocess.TimeoutExpired):
        return {}


def verdict(recorded, service):
    active = service.get("ActiveState")
    if not recorded and active in ("active", "activating"):
        return "RUNNING (preparing; no result yet)"
    if recorded in ("RUNNING", "PREPARED", "BUILDING"):
        if active in ("active", "activating"):
            return "RUNNING"
        if active is None:
            return "UNKNOWN (cannot query service)"
        return "STOPPED/STALE (no live service; not a PASS)"
    if recorded == "PASS" and active == "failed":
        return "CONFLICT (report PASS but service failed)"
    return recorded or "UNKNOWN (no result yet)"


def load_run(spec):
    path = HERE / "out" / spec["directory"]
    state = (read(path / "validation.json") or read(path / "checkpoint.json")
             or read(path / "status.json"))
    if state.get("status") == "HANDED_OFF" and state.get("coverage_output"):
        target = Path(state["coverage_output"])
        handed_off = read(target / "status.json")
        if handed_off:
            path, state = target, handed_off
    if "phase" not in state and "cases" in state:
        state["phase"] = "functional"
    stages = []
    for status in sorted(path.glob("*scheduler/status.json")):
        data = read(status)
        rows = data.get("results", [])
        # Exploration workers return zero after recording ordinary test failures.
        # Scheduler success is not the functional verdict in that mode.
        outcomes = state.get("cases", {})
        if not outcomes and (path / "outcomes").is_dir():
            outcomes = {p.stem: read(p) for p in (path / "outcomes").glob("*.json")}
        if isinstance(outcomes, dict):
            rows = [dict(row, status=outcomes[row["name"]]["status"])
                    if outcomes.get(row.get("name"), {}).get("status") else row for row in rows]
        stages.append((status.parent.name, rows))
    return path, state, stages


def show(spec, detailed=False):
    path, state, stages = load_run(spec)
    service = service_state(spec["service"])
    print(f"[{spec['name']}] {verdict(state.get('status'), service)}")
    print(f"  phase: {state.get('phase', '-')} | service: "
          f"{service.get('ActiveState', 'unknown')}/{service.get('SubState', '-')} "
          f"| PID: {service.get('MainPID', '-')}")
    outcomes = state.get("cases")
    if isinstance(outcomes, dict):
        totals = Counter(row.get("status", "UNKNOWN") for row in outcomes.values())
        pending = {"RUNNING", "PENDING", "PREPARING", "BUILDING", "QUEUED"}
        completed = sum(row.get("status", "UNKNOWN") not in pending for row in outcomes.values())
        print(f"  batch total: {completed}/{state.get('total', '?')} completed | "
              f"reused={sum(bool(row.get('reused')) for row in outcomes.values())} | "
              + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))
        if detailed:
            for name, row in outcomes.items():
                suffix = " (reused)" if row.get("reused") else ""
                print(f"    {row.get('status', 'UNKNOWN'):20} {name}{suffix}")
                if row.get("reason"):
                    print(f"      {row['reason']}")
    for stage, rows in stages:
        counts = Counter(row.get("status", "UNKNOWN") for row in rows)
        print(f"  {stage}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if detailed:
            for row in rows:
                print(f"    {row.get('status', 'UNKNOWN'):20} {row.get('name', '?')}")
    if not stages and not outcomes:
        print("  No scheduler results yet (possibly compiling/preparing).")
    for stop in sorted(path.glob("*scheduler/STOP.json")):
        data = read(stop)
        failure = data.get("failure") or {}
        print(f"  FIRST FAILURE: {failure.get('name', '-')} "
              f"rc={failure.get('returncode', '-')} | {stop}")
        if failure.get("stdout"):
            print(f"  failure log: {failure['stdout']}")
    if state.get("reason"):
        print(f"  reason: {state['reason']}")
    if state.get("coverage_status"):
        print(f"  coverage: {state['coverage_status']} | "
              f"completed aggregate PASS: {state.get('aggregate_passed', '-')}")
    print(f"  output: {path}")


def log_path(spec):
    path, state, stages = load_run(spec)
    for stop in sorted(path.glob("*scheduler/STOP.json")):
        failure = read(stop).get("failure") or {}
        if failure.get("stdout") and Path(failure["stdout"]).is_file():
            return Path(failure["stdout"])
    phase = state.get("phase", "")
    for stage, rows in stages:
        if stage == phase + "-scheduler" or stage == "scheduler":
            running = [r for r in rows if r.get("status") == "RUNNING" and r.get("stdout")]
            if running and Path(running[0]["stdout"]).is_file():
                return Path(running[0]["stdout"])
    candidates = [path / "compile.log"] if phase == "compile" else []
    candidates += [path / "build.log", path / "driver.log", path / "scheduler.log",
                   path / "logs" / (phase + "-scheduler.log")]
    for row in state.get("cases", {}).values():
        if row.get("directory"):
            directory = Path(row["directory"])
            candidates += [directory / "run.vcs.log", directory / "compile.log"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["status", "jobs", "log"], default="status")
    parser.add_argument("run", nargs="?", help="registered name; default: last entry")
    parser.add_argument("--all", action="store_true", help="show every registered campaign")
    parser.add_argument("-n", type=int, default=30, help="log tail lines (default 30)")
    args = parser.parse_args()
    specs = read(HERE / "status_runs.json")
    if not isinstance(specs, list) or not specs:
        parser.error("missing/invalid verification/status_runs.json")
    selected = specs if args.all else ([s for s in specs if s["name"] == args.run]
                                      if args.run else specs[-1:])
    if not selected:
        parser.error("unknown run; choose: " + ", ".join(s["name"] for s in specs))
    if args.n <= 0:
        parser.error("-n must be positive")
    for spec in selected:
        if args.command == "log":
            path = log_path(spec)
            if path:
                print(f"==> {path} <==")
                with path.open(errors="replace") as stream:
                    print("".join(deque(stream, maxlen=args.n)), end="")
            else:
                print(f"[{spec['name']}] No log yet; use status/jobs.")
        else:
            show(spec, args.command == "jobs")


if __name__ == "__main__":
    main()
