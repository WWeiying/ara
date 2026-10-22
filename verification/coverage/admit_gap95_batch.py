"""Independently check three frozen-image scans; union only exact PASS VDBs."""
import argparse
import csv
import json
from pathlib import Path

from admit_gap83_offline import ROOT, require, sha, save, bitmap
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log

OUT = ROOT / "verification/out"
PREFLIGHT = OUT / "gap95-divisor-bound-preflight-20261006-01"
BASE = OUT / "gap94-offline-admitted-701-20261006-01"
DESIGN = OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb"
IMAGE_SHA = "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"
LOAD = lambda path: json.loads(path.read_bytes())


def pin_merge(pins, additions):
    for path, expected in additions.items():
        require(path not in pins or pins[path] == expected, "Conflicting pin: " + path)
        pins[path] = expected


def check_pins(pins):
    for path, expected in pins.items():
        require(sha(Path(path)) == expected, "Evidence drift: " + path)


def vector_exact(result, spec):
    return (result.get("status") == "PASS" and
            result.get("compared_instructions") == spec["expected_vector_instructions"] and
            result.get("compared_bytes") == spec["expected_vector_bytes"] and
            result.get("skipped_unknown_bytes") == 0 and
            result.get("non_bit_exact_instructions") == 0 and
            all(key in result and not result[key] for key in
                ("incomplete_requests", "unretired_requests", "trapped_requests")))


def signature_exact(writes, spec):
    symbols = spec["symbols"]
    return (writes.get(symbols["g75_result"]) == (0x0f, spec["checks"]) and
            writes.get(symbols["g75_result"] + 4) == (0xf0, 0) and
            writes.get(symbols["num_failed"]) == (0x0f, 0) and
            writes.get(symbols["tohost"]) == (0xff, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and not out.exists(), "Fresh output required")
    preflight = LOAD(PREFLIGHT / "preflight-manifest.json")
    require(preflight["status"] == "GAP95_THREE_SPIKE_PREFLIGHTS_PASS_NOT_VCS", "Preflight incomplete")
    specs = preflight["cases"]
    require([s["eew"] for s in specs] == [64, 32, 16], "Wrong case population/order")
    state, old = LOAD(BASE / "status.json"), LOAD(BASE / "combined-bits.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            state["aggregate_passed"] == len(old["tests"]) == len(set(old["tests"])) == 701,
            "Unadmitted baseline")
    require((BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(DESIGN), *old["tests"]], "Baseline input mismatch")
    pins = dict(preflight["pins"])
    pin_merge(pins, LOAD(BASE / "evidence-pins.json"))
    runs = []
    for spec in specs:
        run = OUT / ("gap95-div%d-bound-old-image-20261006-01" % spec["eew"])
        manifest = LOAD(run / "manifest.json")
        simstatus = LOAD(run / "simulation-status.json")
        require(simstatus["status"] in ("SIMULATION_EXITED_NOT_ADMITTED", "SIMULATION_NOT_ADMITTED"),
                "Run not terminal: " + spec["case"])
        pin_merge(pins, manifest["pins"])
        require(sha(Path(manifest["command"][0])) == IMAGE_SHA, "Not frozen old image")
        require("+PRELOAD=" + str(PREFLIGHT / spec["case"] / "input.elf") in manifest["command"],
                "Wrong ELF")
        paths = [run / "manifest.json", run / "simulation-status.json", run / "console.log",
                 *run.glob("*.csv"), run / "run.vcs.log", *sorted((run / "code.vdb").rglob("*"))]
        for path in paths:
            if path.is_file():
                pin_merge(pins, {str(path.resolve()): sha(path)})
        runs.append((spec, run, simstatus))
    for path in [Path(__file__).resolve(), Path(bitmap.__file__),
                 ROOT / "verification/coverage/admit_gap83_offline.py",
                 PREFLIGHT / "preflight-manifest.json", BASE / "combined-bits.json",
                 BASE / "combined-inputs.txt", BASE / "status.json", BASE / "evidence-pins.json",
                 *sorted((ROOT / "verification/ara_verify").glob("*.py"))]:
        pin_merge(pins, {str(path.resolve()): sha(path)})
    check_pins(pins)
    out.mkdir()
    admitted, results = [], []
    for spec, run, simstatus in runs:
        directory = out / spec["case"]
        directory.mkdir()
        try:
            require(simstatus["status"] == "SIMULATION_EXITED_NOT_ADMITTED" and
                    simstatus["returncode"] == 0, "Simulation failed or timed out")
            scalar = compare_commit_prefix(PREFLIGHT / spec["case"] / "spike.trace",
                run / "commit_trace.csv", 0x80000000,
                terminal_tohost_address=spec["symbols"]["tohost"], rvfi_store_data_layout="unshifted")
            save(directory / "scalar-comparison.json", scalar)
            vector = compare_vector_commits(PREFLIGHT / spec["case"] / "spike.trace",
                run / "commit_trace.csv", run / "vector_trace.csv", 0x80000000)
            save(directory / "vector-comparison.json", vector)
            require(scalar["status"] == "TERMINAL_TOHOST_MATCH" and scalar["ara_trap_events"] == 0,
                    "Scalar mismatch/incomplete/trap")
            require(vector_exact(vector, spec), "Vector mismatch/incomplete/non-exact")
            require(not check_contract_log(run / "run.vcs.log"), "Contract failure")
            require((run / "run.vcs.log").read_text().count("Core Test *** SUCCESS ***") == 1,
                    "Software selfcheck failed")
            with (run / "commit_trace.csv").open() as stream:
                writes = {int(r["mem_addr"], 16): (int(r["mem_wmask"], 16), int(r["mem_wdata"], 16))
                          for r in csv.DictReader(stream)
                          if r["event"] == "retire" and int(r["mem_wmask"], 16)}
            require(signature_exact(writes, spec), "DUT signature failed")
            result = dict(case=spec["case"], status="PASS", coverage_admitted=True)
            admitted.append(str(run / "code.vdb"))
        except (ValueError, KeyError, OSError) as error:
            result = dict(case=spec["case"], status="NOT_ADMITTED", reason=str(error), coverage_admitted=False)
        save(directory / "status.json", result)
        results.append(result)
    check_pins(pins)
    combined = old
    if admitted:
        inputs = out / "new-inputs.txt"
        with inputs.open("x") as stream:
            stream.write("\n".join([str(DESIGN), *admitted]) + "\n")
        combined = bitmap.combine(old, bitmap.collect(inputs))
    require(combined["tests"] == [*old["tests"], *admitted], "Union membership differs")
    delta = bitmap.delta(old, combined)
    check_pins(pins)
    save(out / "combined-bits.json", combined)
    save(out / "raw-bitmap-delta.json", delta)
    save(out / "evidence-pins.json", pins)
    with (out / "combined-inputs.txt").open("x") as stream:
        stream.write("\n".join([str(DESIGN), *combined["tests"]]) + "\n")
    result = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", aggregate_passed=len(combined["tests"]),
                  new_passed=len(admitted), cases=results, official_DVE_report=False,
                  rtl_changed=False, new_RTL_signoff=False)
    save(out / "status.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
