#!/usr/bin/env python3

"""Run the derived-real AKV-v2 shape matrix on the scalar and RVV paths."""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SPIKE = REPO_ROOT / "install/riscv-isa-sim/bin/spike"


def write_summary(path, summary):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2) + "\n")
    temporary.replace(path)


def run_logged(command, log_path, *, cwd, env, timeout):
    started = time.monotonic()
    with log_path.open("w") as log:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            return result.returncode, time.monotonic() - started
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {timeout} seconds\n")
            return 124, time.monotonic() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--spike", type=Path, default=DEFAULT_SPIKE)
    parser.add_argument("--mode", action="append", choices=("ref", "rvv"))
    parser.add_argument("--case-regex")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    import re

    capture_root = args.capture_root.resolve()
    manifest_path = capture_root / "replay/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    cases = [case["id"] for case in manifest["cases"]]
    if args.case_regex:
        pattern = re.compile(args.case_regex)
        cases = [case_id for case_id in cases if pattern.search(case_id)]
    if not cases:
        raise SystemExit("no AKV-v2 cases selected")

    modes = args.mode or ["ref", "rvv"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output = (args.output or
              REPO_ROOT / "hardware" / f"akv_v2_shape_spike_{timestamp}")
    output.mkdir(parents=True, exist_ok=False)

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    expected_results = len(cases) * len(modes)
    summary = {
        "schema_version": 2,
        "classification": "derived-real shape/numerical verification",
        "status": "running",
        "started_at": started_at.isoformat(),
        "capture_root": str(capture_root),
        "capture_model": manifest.get("model"),
        "capture_source": manifest.get("source"),
        "spike": str(args.spike.resolve()),
        "isa": "rv64gcv_zfh",
        "varch": "vlen:1024,elen:64",
        "modes": modes,
        "cases": cases,
        "expected_results": expected_results,
        "completed_results": 0,
        "passed": 0,
        "failed": 0,
        "remaining": expected_results,
        "results": [],
    }
    summary_path = output / "summary.json"
    write_summary(summary_path, summary)

    env = os.environ.copy()
    env["Q4KM_CAPTURE_ROOT"] = str(capture_root)
    failed = 0
    for index, case_id in enumerate(cases, start=1):
        safe_case = case_id.replace("/", "_")
        for mode in modes:
            tag = f"{safe_case}_{mode}"
            build_log = output / f"{tag}.build.log"
            run_log = output / f"{tag}.run.log"
            make_command = [
                "make", "-s", "-C", "apps",
                "bin/llama_q4km_operator.spike",
                f"def_args_llama_q4km_operator={case_id} {mode}",
            ]
            build_rc, build_seconds = run_logged(
                make_command, build_log, cwd=REPO_ROOT, env=env,
                timeout=args.timeout,
            )
            run_rc = None
            run_seconds = 0.0
            if build_rc == 0:
                run_command = [
                    str(args.spike),
                    "--isa=rv64gcv_zfh",
                    "--varch=vlen:1024,elen:64",
                    "apps/bin/llama_q4km_operator.spike",
                ]
                run_rc, run_seconds = run_logged(
                    run_command, run_log, cwd=REPO_ROOT, env=env,
                    timeout=args.timeout,
                )
            else:
                run_log.write_text("not run because build failed\n")

            passed = build_rc == 0 and run_rc == 0
            failed += not passed
            record = {
                "case": case_id,
                "mode": mode,
                "passed": passed,
                "build_rc": build_rc,
                "run_rc": run_rc,
                "build_seconds": round(build_seconds, 3),
                "run_seconds": round(run_seconds, 3),
                "build_log": build_log.name,
                "run_log": run_log.name,
            }
            summary["results"].append(record)
            summary["completed_results"] = len(summary["results"])
            summary["passed"] = summary["completed_results"] - failed
            summary["failed"] = failed
            summary["remaining"] = expected_results - summary["completed_results"]
            write_summary(summary_path, summary)
            print(
                f"[{index:02d}/{len(cases):02d}] {case_id} {mode}: "
                f"{'PASS' if passed else 'FAIL'}",
                flush=True,
            )

    summary["status"] = "completed"
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    write_summary(summary_path, summary)
    print(f"summary: {summary_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
