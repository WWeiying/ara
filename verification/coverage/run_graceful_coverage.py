#!/usr/bin/env python3
"""Independent bounded replay with SIGINT coverage salvage; never promotes timeouts.

No existing campaign is stopped or resumed. Use a dedicated systemd service with
KillMode=control-group for nested-process cleanup. Partial exploration requires
--reference-result from a valid same-image raw coverage sample, so a truncated
file with a parseable prefix cannot silently shrink the point denominator.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

from merge_exploration import validate_sample
from run_verilator_coverage import SUCCESS, iter_raw_points, log_tail, sha256, summarize_lcov

CYCLE_STOP = re.compile(r"Simulation timeout of .* cycles reached, shutting down simulation\.")
ENV_ERROR = re.compile(r"error while loading shared libraries|No space left on device|"
                       r"Cannot allocate memory|std::bad_alloc|Permission denied", re.I)


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run_process(command, output, timeout_s, grace_s=120):
    started = time.monotonic()
    events = []
    wall_timeout = killed = False
    with (output / "sim.log").open("w") as log:
        child = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        def send(sig):
            if child.poll() is None:
                try:
                    os.killpg(child.pid, sig)
                    events.append({"signal": signal.Signals(sig).name,
                                   "elapsed_s": round(time.monotonic() - started, 3)})
                except ProcessLookupError:
                    pass
        try:
            try:
                child.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                wall_timeout = True  # Latched before signal/exit races, never cleared.
                send(signal.SIGINT)
                try:
                    child.wait(timeout=grace_s)
                except subprocess.TimeoutExpired:
                    killed = True
                    send(signal.SIGKILL)
                    child.wait(timeout=10)
        finally:
            if child.poll() is None:
                send(signal.SIGKILL)
                child.wait(timeout=10)
    return {"pid": child.pid, "sim_returncode": child.returncode, "wall_timeout": wall_timeout,
            "hard_killed": killed, "signals": events,
            "simulation_elapsed_s": round(time.monotonic() - started, 3)}


def raw_points(path):
    # iter_raw_points intentionally skips non-point lines; reject unexpected or
    # unterminated records first to avoid accepting an interrupted write prefix.
    with path.open(encoding="utf-8", errors="strict") as stream:
        for line in stream:
            if not line.endswith("\n") or (line.strip() and not line.startswith(("#", "C '"))):
                raise ValueError("incomplete/unrecognized raw coverage record")
    points = set()
    for props, count in iter_raw_points(path):
        if count < 0 or not props.get("t") or not props.get("f"):
            raise ValueError("invalid raw point metadata/count")
        points.add(tuple(sorted(props.items())))
    if not points:
        raise ValueError("no raw coverage points")
    return points


def reference_points(path, image_hash):
    result_hash = sha256(path)
    evidence = validate_sample(path)
    if evidence["image_sha256"] != image_hash:
        raise ValueError("reference coverage uses a different simulator image")
    raw = Path(evidence["coverage"])
    points = raw_points(raw)
    if sha256(raw) != evidence["coverage_sha256"] or sha256(path) != result_hash:
        raise ValueError("reference changed while reading")
    return points, {str(path): result_hash, str(raw): evidence["coverage_sha256"]}


def report_raw(reporter, coverage, info, output):
    command = [str(reporter), "--write-info", str(info), str(coverage)]
    process = subprocess.run(command, cwd=output, capture_output=True, text=True,
                             timeout=60, check=False)
    if process.returncode or not info.is_file() or not info.stat().st_size:
        raise RuntimeError(f"coverage reporter failed: {process.returncode}: {process.stdout}{process.stderr}")
    return {"report_command": command, "report_returncode": process.returncode,
            "report_output": process.stdout + process.stderr,
            "coverage_info_sha256": sha256(info), "raw_coverage": summarize_lcov(info)}


def run_case(simv, elf, reporter, output, term_cycles=100000, timeout_s=900,
             grace_s=120, tohost_addr=None, reference=None):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {"status": "ERROR", "raw_valid": False, "exploration_eligible": False,
              "passed_only": False, "replay_pass_eligible": False, "timed_out": False, "timeout_s": timeout_s,
              "grace_s": grace_s, "term_cycles": term_cycles, "tohost_addr": tohost_addr,
              "source_audit_required_for_passed_only": True,
              "runner": "graceful-v1", "signals": [], "infrastructure_errors": []}
    pins = {}
    try:
        simv, elf, reporter = (path.resolve(strict=True) for path in (simv, elf, reporter))
        pins = {str(path): sha256(path) for path in (simv, elf, reporter)}
        expected_points = None
        if reference:
            reference = reference.resolve(strict=True)
            expected_points, reference_pins = reference_points(reference, pins[str(simv)])
            pins.update(reference_pins)
            result.update(reference_result=str(reference), reference_pins=reference_pins)
        frozen_simv, frozen_elf = output / "simv", output / "input.elf"
        shutil.copy2(simv, frozen_simv)
        shutil.copy2(elf, frozen_elf)
        if sha256(frozen_simv) != pins[str(simv)] or sha256(frozen_elf) != pins[str(elf)]:
            raise RuntimeError("input changed while freezing")
        pins.update({str(frozen_simv): pins[str(simv)], str(frozen_elf): pins[str(elf)]})
        coverage, info = output / "coverage.dat", output / "coverage.info"
        command = [str(frozen_simv), f"--term-after-cycles={term_cycles}",
                   f"--meminit=ram,{frozen_elf},elf", f"+verilator+coverage+file+{coverage}"]
        if tohost_addr is not None:
            command.append(f"+COMMIT_TOHOST={tohost_addr:016x}")
        result.update(simv=str(frozen_simv), simv_sha256=pins[str(simv)], elf=str(frozen_elf),
                      elf_sha256=pins[str(elf)], source_simv=str(simv), source_elf=str(elf),
                      reporter_sha256=pins[str(reporter)], command=command, status="RUNNING")
        save(output / "result.json", result)
        result.update(run_process(command, output, timeout_s, grace_s))
        log = (output / "sim.log").read_text(errors="replace")
        result["self_check_pass"] = bool(SUCCESS.search(log))
        result["cycle_limit_reached"] = bool(CYCLE_STOP.search(log))
        result["timed_out"] = result["wall_timeout"] or result["cycle_limit_reached"]
        result["termination"] = ("wall-timeout" if result["wall_timeout"] else
                                 "cycle-limit" if result["cycle_limit_reached"] else "natural")
        result["status"] = "TIMEOUT" if result["timed_out"] else "FAIL"
        if ENV_ERROR.search(log):
            raise RuntimeError("simulator environment failure")
        if result["sim_returncode"] not in (0, 1, -6) and not result["timed_out"]:
            raise RuntimeError(f"unexpected simulator exit: {result['sim_returncode']}")
        natural_pass = (not result["timed_out"] and result["sim_returncode"] == 0
                        and result["self_check_pass"])
        if coverage.is_file() and coverage.stat().st_size:
            try:
                raw_hash = sha256(coverage)
                points = raw_points(coverage)
                if expected_points is not None and points != expected_points:
                    raise ValueError(f"point denominator mismatch: missing={len(expected_points-points)}, "
                                     f"extra={len(points-expected_points)}")
                result.update(report_raw(reporter, coverage, info, output))
                if sha256(coverage) != raw_hash:
                    raise ValueError("raw coverage changed during validation")
                result.update(raw_valid=True, raw_points=len(points),
                              denominator_check="PASS" if expected_points is not None else "NOT_CHECKED",
                              exploration_eligible=expected_points is not None or natural_pass)
            except ValueError as error:
                result["raw_rejection"] = str(error)
                if natural_pass:
                    raise RuntimeError("passing simulation produced invalid coverage") from error
        elif natural_pass:
            raise RuntimeError("passing simulation did not produce coverage")
        if natural_pass:
            # Only a queue with a matching independent source audit can promote
            # this replay to a passed-only collection.
            result.update(status="PASS", replay_pass_eligible=True)
        elif not result["timed_out"]:
            result["reason"] = "simulation or in-program self-check failed"
    except Exception as error:
        result["infrastructure_errors"].append(f"{type(error).__name__}: {error}")
    finally:
        for path, expected in pins.items():
            if not Path(path).is_file() or sha256(Path(path)) != expected:
                result["infrastructure_errors"].append(f"input drift: {path}")
        log = output / "sim.log"
        if log.is_file():
            result.update(sim_log_sha256=sha256(log), sim_log_tail=log_tail(log))
        raw = output / "coverage.dat"
        if raw.is_file():
            result.update(coverage_sha256=sha256(raw), coverage_bytes=raw.stat().st_size)
        if result["infrastructure_errors"]:
            result.update(status="TIMEOUT" if result["timed_out"] else "ERROR",
                          raw_valid=False, exploration_eligible=False, passed_only=False,
                          replay_pass_eligible=False)
        result["partial"] = result["status"] != "PASS"
        result["elapsed_s"] = round(time.monotonic() - started, 3)
        save(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verilator-coverage", type=Path, required=True)
    parser.add_argument("--reference-result", type=Path)
    parser.add_argument("--term-cycles", type=int, default=100000)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--grace", type=int, default=120)
    parser.add_argument("--tohost-addr", type=lambda value: int(value, 0))
    args = parser.parse_args()
    if not (1 <= args.term_cycles <= 2147483647 and args.timeout > 0 and 1 <= args.grace <= 120):
        parser.error("invalid cycle/time budget; grace must be 1..120 seconds")
    if args.tohost_addr is not None and not (0x80000000 <= args.tohost_addr < 1 << 64 and args.tohost_addr % 8 == 0):
        parser.error("tohost must be aligned and inside RAM address space")
    result = run_case(args.simv, args.elf, args.verilator_coverage, args.output,
                      args.term_cycles, args.timeout, args.grace, args.tohost_addr, args.reference_result)
    print(f"{result['status']}: raw_valid={result['raw_valid']} "
          f"exploration_eligible={result['exploration_eligible']}: {args.output}")
    return 2 if result["infrastructure_errors"] else 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
