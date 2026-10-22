#!/usr/bin/env python3
"""Derive the verified historical689 raw union; no DVE or waiver approval."""
import argparse
import json
from pathlib import Path

import coverage_bitmap_delta as bitmap
import verify_gap82_offline as evidence

ROOT = evidence.ROOT
OUT = ROOT / "verification/out"
BASELINE = OUT / "gap81-dve-only-retry-20261006-01"
PREPARED = OUT / "gap82-combine-complete-baseline-20261006-01"
SINGLE_INPUTS = OUT / "gap82-single-inputs-20261006-01.txt"


def run(output):
    require = evidence.require
    output = output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.exists(),
            "Fresh independent output required")
    pins = evidence.target.read(PREPARED / "preparation-pins.json")
    for path, digest in pins.items():
        require(bitmap.digest(Path(path)) == digest, "Preparation drift: " + path)
    status = evidence.target.read(BASELINE / "status.json")
    require(status["coverage_status"] == "COMPLETE" and status["aggregate_passed"] == 688,
            "Completed historical688 baseline required")
    description = evidence.target.read(PREPARED / "single-case-description.json")
    require(description["baseline"] == str(BASELINE) and description["proposed_cases"] == 689,
            "Different combine preparation")
    before = evidence.target.read(BASELINE / "combined-bits.json")
    members = (PREPARED / "proposed-inputs.txt").read_text().splitlines()
    single = SINGLE_INPUTS.read_text().splitlines()
    require(single == [members[0], description["case_vdb"]] and
            members[1:] == [*before["tests"], description["case_vdb"]] and
            len(members) == len(set(members)) == 690, "Different/duplicate VDB population")
    for path, digest in before["input_hashes"].items():
        require(bitmap.digest(Path(path)) == digest, "Historical bitmap input drift: " + path)
    sample = bitmap.collect(SINGLE_INPUTS)
    after = bitmap.combine(before, sample)
    require(after["tests"] == members[1:], "Union membership mismatch")
    delta = bitmap.delta(before, after)
    for path, digest in {**before["input_hashes"], **sample["input_hashes"], **pins}.items():
        require(bitmap.digest(Path(path)) == digest, "Input changed during union: " + path)
    output.mkdir()
    for name, value in (("combined-bits.json", after), ("raw-bitmap-delta.json", delta)):
        evidence.frozen.save(output / name, value)
    with (output / "combined-inputs.txt").open("x") as stream:
        stream.write("\n".join(members) + "\n")
    evidence.frozen.save(output / "provenance.json", dict(
        status="RAW_DIAGNOSTIC_UNION_COMPLETE", historical_tests=689,
        baseline=str(BASELINE), preparation=str(PREPARED),
        preparation_pins=pins, single_inputs_sha256=bitmap.digest(SINGLE_INPUTS),
        script_sha256=bitmap.digest(Path(__file__)),
        outputs={str(p): bitmap.digest(p) for p in output.iterdir() if p.is_file()},
        dve_run=False, waivers_applied=False, new_rtl_signoff=False))
    return delta["metrics"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
