"""Run only untouched cases from a frozen paired campaign with full event traces."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def run_case(case: dict, simv: Path, runner: Path, output: Path,
             trace_limit: int, timeout_seconds: int) -> dict:
    name, mode = case["name"], case["mode"]
    destination = output / name / mode
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    log = output / "logs" / f"{name}-{mode}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update({
        "ARA_CONTRACT_TRACE_LIMIT": str(trace_limit),
        "ARA_UVM_TRACE_LIMIT": str(trace_limit),
        "ARA_VCS_TIMEOUT_SECONDS": str(timeout_seconds),
    })
    command = [str(runner), str(simv), case["elf"], case["testcase"],
               str(destination)]
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                   env=environment, check=False)
    result = {"name": name, "mode": mode, "output": str(destination),
              "log": str(log), "returncode": completed.returncode,
              "status": "FAIL"}
    evidence = destination / "uvm_result.json"
    if evidence.is_file():
        result["status"] = json.loads(evidence.read_text(encoding="utf-8"))["status"]
    if completed.returncode or result["status"] != "PASS":
        result["status"] = "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--trace-limit", type=int, default=400000)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()
    if min(args.jobs, args.trace_limit, args.timeout_seconds) <= 0:
        parser.error("jobs, trace limit and timeout must be positive")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    frozen_plan = args.plan.read_bytes()
    plan = json.loads(frozen_plan)
    pending = [case for case in plan["cases"] if case.get("status") is None]
    if not pending:
        parser.error("no untouched campaign cases remain")
    runner = args.runner.resolve(strict=True)
    simv = Path(plan["simv"]).resolve(strict=True)
    if digest(runner) != plan["runner_sha256"]:
        parser.error("runner differs from frozen campaign")
    if digest(simv) != plan["simv_sha256"]:
        parser.error("simulator differs from frozen campaign")
    for case in pending:
        if digest(Path(case["elf"])) != case["elf_sha256"]:
            parser.error(f"frozen ELF changed: {case['name']}/{case['mode']}")
    args.output.mkdir(parents=True)
    write_json(args.output / "frozen_plan.json", {
        "plan": str(args.plan.resolve()),
        "plan_sha256": hashlib.sha256(frozen_plan).hexdigest(),
        "simv": str(simv), "simv_sha256": plan["simv_sha256"],
        "runner": str(runner), "runner_sha256": plan["runner_sha256"],
        "trace_limit": args.trace_limit, "cases": pending,
    })
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(run_case, case, simv, runner, args.output,
                                   args.trace_limit, args.timeout_seconds)
                   for case in pending]
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as error:
                results.append({"status": "FAIL", "reason": str(error)})
            write_json(args.output / "results.json", results)
    status = "PASS" if all(row["status"] == "PASS" for row in results) else "FAIL"
    write_json(args.output / "summary.json", {"status": status, "results": results})
    print(f"{status}: {args.output / 'summary.json'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
