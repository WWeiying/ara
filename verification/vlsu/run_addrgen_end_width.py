#!/usr/bin/env python3
"""Compare the current split-end arithmetic with pinned HEAD at equal widths."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
RTL = Path("hardware/src/vlsu/addrgen.sv")
GENERATOR = Path("verification/timing/generate_closure_checks.py")
BENCH = Path("verification/timing/addrgen_end_equivalence_tb.sv")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("each phase timeout must be between 1 and 300 seconds")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / "inputs"
    inputs.mkdir()
    result = {
        "status": "failed",
        "scope": "Sampled set_end_addr arithmetic equivalence, current versus HEAD, equal virtual widths",
        "exclusions": [
            "AXI48/VA64 integration, MMU, queues and exception behavior",
            "Physical address representability and synthesis/timing closure",
            "Exhaustive equivalence or measured branch coverage",
        ],
        "commands": [],
        "sources": {},
    }
    started = time.monotonic()

    def capture(command):
        return subprocess.check_output(command, cwd=ROOT, text=True).strip()

    def snapshot(relative):
        data = (ROOT / relative).read_bytes()
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        result["sources"][str(relative)] = sha(data)
        return target

    def run(command, log):
        bounded = ["timeout", "--kill-after=10s", str(args.timeout), *command]
        result["commands"].append(shlex.join(bounded))
        with (out / log).open("w") as stream:
            completed = subprocess.run(bounded, cwd=out, stdout=stream,
                                       stderr=subprocess.STDOUT, check=False)
        result[log + "_returncode"] = completed.returncode
        if completed.returncode:
            raise RuntimeError(f"{log}: exit {completed.returncode}")

    try:
        commit = capture(["git", "rev-parse", "HEAD"])
        result["reference_commit"] = commit
        baseline = subprocess.check_output(
            ["git", "show", f"{commit}:{RTL}"], cwd=ROOT)
        (inputs / "addrgen.head.sv").write_bytes(baseline)
        result["reference_sha256"] = sha(baseline)
        current = snapshot(RTL).read_text()
        generator = snapshot(GENERATOR)
        bench = snapshot(BENCH)
        snapshot(Path("verification/timing/Makefile"))
        snapshot(Path(__file__).resolve().relative_to(ROOT))
        namespace = {"__file__": str(ROOT / GENERATOR), "__name__": "addrgen_width_generator"}
        exec(compile(generator.read_text(), str(generator), "exec"), namespace)
        address_module = namespace["address_module"]
        cones = out / "addrgen_cones.sv"
        cones.write_text(address_module("addrgen_end_dut", current) +
                         address_module("addrgen_end_reference", baseline.decode()))
        result["cones_sha256"] = sha(cones.read_bytes())
        packages = capture([
            "make", "--no-print-directory", "-s", "-C", str(ROOT / "verification/timing"),
            "--eval=print-addrgen-packages: ; @printf '%s\\n' '$(PACKAGES)'",
            "print-addrgen-packages",
        ])
        package_paths = [Path(path).relative_to(ROOT) for path in shlex.split(packages)]
        if not package_paths:
            raise RuntimeError("empty timing Makefile PACKAGES")
        frozen_packages = [str(snapshot(path)) for path in package_paths]
        run([args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
             "-l", "compile.log", *frozen_packages, str(cones), str(bench),
             "-top", "addrgen_end_equivalence_tb", "-o", "simv"], "compile.stdout.log")
        run([str(out / "simv"), "+ntb_random_seed=1", "-l", "run.log"], "run.stdout.log")
        log = (out / "run.log").read_text()
        cases = [tuple(map(int, match)) for match in re.findall(
            r"AddrGen case PASS address=(\d+) data=(\d+) vlen=(\d+) checks=(\d+)", log)]
        expected = {(address, data, vlen, 12000) for address in (32, 64)
                    for data in (64, 128, 256) for vlen in (1024, 65536)}
        if len(cases) != 12 or set(cases) != expected:
            raise RuntimeError(f"incomplete or duplicate configuration results: {cases}")
        if "AddrGen equivalence PASS configurations=12 checks=144000" not in log:
            raise RuntimeError("missing final PASS marker")
        if re.search(r"Fatal:|Error:|\$fatal", log):
            raise RuntimeError("simulation reported an error")
        result.update(status="passed", checks=144000, configurations=sorted(cases), seed=1)
        result["stimulus"] = (
            "12000 trials/configuration; first 4096 addresses are all-ones XOR trial, "
            "then random addresses; zero/one/max and random lengths; all effective "
            "bus widths. High addresses/page/wrap boundaries are exercised by stimulus; "
            "carry/borrow branch coverage is not separately instrumented."
        )
    except Exception as error:
        result["error"] = str(error)
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "elapsed_seconds")}, indent=2))
    print(out / "result.json")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
