"""Run one sealed GAP95 case on the old image; no coverage admission."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
PRE = OUT / "gap95-divisor-bound-preflight-20261006-01"
PRE_SEAL = "cec2446aacc18553a4c7d8c4941cd99392cf92be8a5930b9279123e9665f9008"
PLAN = OUT / "closure90-current-20261005-01/plan.json"
PLAN_SEAL = "7dba67ac552e0f0a65fa1df6f8f6e8ec2e3469da738ca88e9ee965e33a9ecf49"
IMAGE = OUT / "repaired-aligned-build-20260930-01/sim/simv"
CASES = {"div64": (64, 32, 1616), "div32": (32, 64, 3152), "div16": (16, 128, 6224)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bound(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Sealed manifest changed: " + str(path))
    return json.loads(raw)


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def merge_pins(left, right):
    merged = dict(left)
    if not isinstance(right, dict) or not right:
        raise ValueError("Missing pin inventory")
    for path, expected in right.items():
        if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(expected, str):
            raise ValueError("Malformed pin")
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("Malformed pin hash")
        if path in merged and merged[path] != expected:
            raise ValueError("Conflicting evidence pin: " + path)
        merged[path] = expected
    return merged


def check(pins):
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError("Pinned input changed: " + path)


def validate_preflight(pre, case):
    if case not in CASES:
        raise ValueError("Unknown case")
    if (pre.get("status") != "GAP95_THREE_SPIKE_PREFLIGHTS_PASS_NOT_VCS" or
            pre.get("coverage_admitted") is not False or pre.get("rtl_changed") is not False or
            pre.get("measured_raw_increment") is not None):
        raise ValueError("Preflight not qualified for simulation")
    rows = pre.get("cases", [])
    names = [r.get("case") for r in rows]
    expected_names = {"vgap95_div%d_bound" % s[0] for s in CASES.values()}
    if len(names) != 3 or set(names) != expected_names:
        raise ValueError("Preflight case population differs")
    selected = None
    for key, (width, vl, count) in CASES.items():
        name = "vgap95_div%d_bound" % width
        row = next(r for r in rows if r["case"] == name)
        if (row.get("status") != "SPIKE_SELF_CHECK_PASS_NOT_COVERAGE_ADMITTED" or
                row.get("eew") != width or row.get("vl") != vl or row.get("checks") != count or
                row.get("expected_vector_instructions") != 48 or row.get("expected_vector_bytes") != 12288 or
                row.get("symbols") != dict(tohost=0x80001000, g75_result=0x80002288,
                                            g75_trap=0x80002200, num_failed=0x80002280)):
            raise ValueError("Case preflight contract differs: " + name)
        for filename in ("input.elf", "spike.trace", "preflight.json"):
            if str(PRE / name / filename) not in pre.get("pins", {}):
                raise ValueError("Case artifact is unpinned: " + name + "/" + filename)
        if key == case:
            selected = row
    return selected


def make_command(row, output):
    name = row["case"]
    return [str(IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(PRE / name / "input.elf"), "+TESTCASE=" + name,
            "+COMMIT_TOHOST=%x" % row["symbols"]["tohost"],
            "+COMMIT_TRACE=" + str(output / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"),
            "-cm_name", name]


def prepare(case, output):
    output = Path(output).absolute()
    if output.parent != OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh independent direct output required")
    prefile = PRE / "preflight-manifest.json"
    pre = read_bound(prefile, PRE_SEAL)
    row = validate_preflight(pre, case)
    plan = read_bound(PLAN, PLAN_SEAL)
    if plan.get("simv") != str(IMAGE) or str(IMAGE) not in plan.get("image", {}):
        raise ValueError("Old image identity differs")
    pins = merge_pins({}, pre["pins"])
    pins = merge_pins(pins, plan["image"])
    pins = merge_pins(pins, {str(prefile): PRE_SEAL, str(PLAN): PLAN_SEAL})
    for path in (Path(__file__).resolve(), ROOT / "verification/coverage/test_run_gap95_simulation.py"):
        pins = merge_pins(pins, {str(path): digest(path)})
    check(pins)
    return output, dict(case=case, preflight=row, pins=pins, command=make_command(row, output),
                        timeout_s=600, coverage_admitted=False, rtl_changed=False,
                        new_RTL_signoff=False, admission_performed=False)


def run(output, manifest):
    # Recheck immediately before launching and after exit, including failure paths.
    check(manifest["pins"])
    output.mkdir()
    save(output / "manifest.json", manifest)
    try:
        check(manifest["pins"])
        with (output / "console.log").open("x") as log:
            result = subprocess.run(manifest["command"], cwd=output, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=600, check=True)
        if result.returncode != 0:
            raise ValueError("Nonzero simulator exit")
        check(manifest["pins"])
        save(output / "simulation-status.json", dict(status="SIMULATION_EXITED_NOT_ADMITTED",
             returncode=result.returncode, case=manifest["case"], coverage_admitted=False,
             admission_performed=False))
    except Exception as error:
        pin_error = None
        try:
            check(manifest["pins"])
        except Exception as drift:
            pin_error = str(drift)
        save(output / "simulation-status.json", dict(status="SIMULATION_NOT_ADMITTED",
             reason="%s: %s" % (type(error).__name__, error), post_failure_pin_error=pin_error,
             case=manifest["case"], coverage_admitted=False, admission_performed=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(CASES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, manifest = prepare(args.case, args.output)
    run(output, manifest)


if __name__ == "__main__":
    main()
