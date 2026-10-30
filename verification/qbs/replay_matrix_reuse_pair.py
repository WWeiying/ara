#!/usr/bin/env python3
"""Replay equal-output QBS schedules with bounded AXI response gaps.

This is a bandwidth sensitivity experiment, not a calibrated DDR model.
The verified baseline supplies the image and real-data vectors. No rebuild,
new random input, numerical tolerance change, or RTL modification is made.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal

from run_half_scale_soc import atomic_json, digest, hashes, run_command
from run_matrix_reuse_pair import SLICES, checked_log, outputs

PROFILES = {"q4_K": (1, 1536), "q6_K": (2, 8960)}
WORK_KEYS = ("weight", "activation", "payload", "ranges", "dot")


def unchanged(pins):
    for name, expected in pins.items():
        if digest(Path(name)) != expected:
            raise ValueError("Source/input/image drift: " + name)


def check_profile(log, profile):
    matches = re.findall(r"QBS end-to-end case 0 PASS profile=(\d+) ", log)
    if matches != [str(PROFILES[profile][0])]:
        raise ValueError("Wrong executed profile")


def compare_work(baseline, candidate):
    if any(baseline["traffic"][key] != candidate["traffic"][key] for key in WORK_KEYS):
        raise ValueError("Response-gap replay changed work or traffic")
    for key in ("issued", "cast_issue", "half_issue"):
        if baseline["fp"][key] != candidate["fp"][key]:
            raise ValueError("Response-gap replay changed arithmetic work")


def summarize(cases):
    result = {}
    for profile, (_, k) in PROFILES.items():
        schedules = {}
        for group in ("m4", "m8"):
            parts = [cases[profile + "_" + group + suffix] for suffix in ("a", "b")]
            schedules[group] = {
                "cycles": sum(part["cycles"] for part in parts),
                "phases": {key: sum(part["phases"][key] for part in parts)
                           for key in parts[0]["phases"]},
                "traffic": {key: sum(part["traffic"][key] for part in parts)
                            for key in WORK_KEYS},
            }
        m4, m8 = schedules["m4"], schedules["m8"]
        macs = 8 * 32 * k
        floor = macs // 32
        if m4["traffic"]["dot"] != floor or m8["traffic"]["dot"] != floor:
            raise ValueError("Dot work differs from 32-products/cycle bound")
        delta = {key: m8["phases"][key] - m4["phases"][key] for key in m4["phases"]}
        if sum(delta.values()) != m8["cycles"] - m4["cycles"]:
            raise ValueError("Cycle delta does not match phase delta")
        result[profile] = {
            "shape_mnk": [8, 32, k], "macs": macs,
            "ideal_integer_issue_floor_cycles": floor,
            "schedules": schedules, "m8_minus_m4_phase_cycles": delta,
            "m8_speedup_over_m4": m4["cycles"] / m8["cycles"],
            "m4_integer_issue_fraction": floor / m4["cycles"],
            "m8_integer_issue_fraction": floor / m8["cycles"],
        }
    return result


def verify_baseline(base):
    status_path = base / "status.json"
    status = json.loads(status_path.read_text())
    if status.get("state") != "PASS" or status.get("child_pid") is not None:
        raise ValueError("Baseline is not a completed passing run")
    pins = dict(status["sources_and_inputs"])
    if not pins:
        raise ValueError("Empty baseline manifest")
    pins[str(status_path)] = digest(status_path)
    expected_cases = {profile + "_" + item[0] for profile in PROFILES for item in SLICES}
    if set(status["cases"]) != expected_cases:
        raise ValueError("Incomplete or unexpected baseline cases")
    for profile, (_, k) in PROFILES.items():
        values, flags = {"m4": {}, "m8": {}}, {"m4": 0, "m8": 0}
        for name, first_m, m, first_n, n in SLICES:
            case = profile + "_" + name
            directory = base / case
            log, vector = directory / "run.log", directory / "input.vectors"
            recorded = status["cases"][case]
            if digest(log) != recorded["log_sha256"] or digest(vector) != recorded["vector_sha256"]:
                raise ValueError("Baseline case artifact drift")
            parsed = checked_log(log.read_text(), m, n, k // 256)
            check_profile(log.read_text(), profile)
            if any(recorded[key] != value for key, value in parsed.items()):
                raise ValueError("Baseline status differs from log")
            if recorded["coordinates"] != [first_m, m, first_n, n, k]:
                raise ValueError("Baseline coordinates differ")
            text = vector.read_text()
            group = name[:2]
            mapped = outputs(text, first_m, m, first_n, n)
            if values[group].keys() & mapped.keys():
                raise ValueError("Duplicate baseline coordinates")
            values[group].update(mapped)
            headers = re.findall(r"^CMD .+ ([0-9a-fA-F]+)$", text, re.M)
            if len(headers) != 1:
                raise ValueError("Missing unique vector command")
            flags[group] |= int(headers[0], 16)
            pins[str(log)] = digest(log)
            pins[str(vector)] = digest(vector)
        if values["m4"] != values["m8"] or len(values["m4"]) != 256 or flags["m4"] != flags["m8"]:
            raise ValueError("Baseline is not equal-output/equal-flags")
    image = base / "build/simv"
    libraries = list(Path(str(image) + ".daidir").rglob("*.so"))
    if not libraries or not os.access(image, os.X_OK) or any(str(p) not in pins for p in [image, *libraries]):
        raise ValueError("Unpinned simulator image")
    unchanged(pins)
    return status, pins, image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gaps", nargs="+", type=int, default=[2, 4])
    args = parser.parse_args()
    if len(set(args.gaps)) != len(args.gaps) or any(gap < 1 or gap > 8 for gap in args.gaps):
        parser.error("gaps must be distinct values in 1..8")
    base, out = args.baseline.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"state": "preparing", "pid": os.getpid(), "child_pid": None,
             "scope": __doc__, "cases": {}, "summaries": {}}
    def save():
        atomic_json(out / "status.json", state)
    def interrupted(signum, _frame):
        raise InterruptedError(f"signal {signum}")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    save()
    try:
        baseline, pins, image = verify_baseline(base)
        pins.update(hashes([Path(__file__).resolve()]))
        state.update(state="running", pins=pins, baseline=str(base),
                     gaps=args.gaps, planned_cases=8 * len(args.gaps))
        state["summaries"]["gap0"] = summarize(baseline["cases"])
        for gap in args.gaps:
            cases = {}
            for profile, (_, k) in PROFILES.items():
                for name, _, m, _, n in SLICES:
                    unchanged(pins)
                    case = profile + "_" + name
                    directory = out / f"gap{gap}" / case
                    directory.mkdir(parents=True)
                    log = directory / "run.log"
                    vector = base / case / "input.vectors"
                    command = [str(image), "-l", str(log), "+QBS_FUNCTIONAL_ONLY", "+QBS_FP_PROBE",
                               "+QBS_COMMAND_VECTOR_FILE=" + str(vector), f"+QBS_RESPONSE_GAP={gap}"]
                    state.update(current_case=f"gap{gap}/{case}", command=command)
                    def started(pid):
                        state["child_pid"] = pid
                        save()
                    try:
                        rc = run_command(command, directory / "console.log", 240, os.environ.copy(), started)
                        if rc != 0:
                            raise RuntimeError(f"VCS exited {rc}: {log}")
                    finally:
                        state["child_pid"] = None
                        save()
                    measured = checked_log(log.read_text(), m, n, k // 256)
                    check_profile(log.read_text(), profile)
                    compare_work(baseline["cases"][case], measured)
                    measured["log_sha256"] = digest(log)
                    pins[str(log)] = measured["log_sha256"]
                    state["cases"][f"gap{gap}/{case}"] = measured
                    cases[case] = measured
                    save()
            state["summaries"][f"gap{gap}"] = summarize(cases)
        unchanged(pins)
        state["state"] = "PASS"
    except BaseException as error:
        state.update(state="FAIL", error=repr(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
