"""Sealed native AKV candidate against formal719: diagnostic proposal, no admission."""
import argparse
import json
from pathlib import Path

import check_akv_column_boundary_v5_offline as c

life, require = c.life, c.require
BASE = life.OUT / "gap102b-offline-admitted-719-20261006-01"
CANDIDATE = life.OUT / "akv-column-boundary-v5-native-candidate-20261006-01"
CANDIDATE_SEAL = "0cb09bfa36605257f09ef3ff3a81e2c1e723973322039298722bc5804d06349e"


def population(before, single):
    new = str(c.RUN / "code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 719 and
            single["tests"] == [new] and new not in before["tests"], "Wrong719/new singleton population")
    require(not any("akv-column-boundary-old-image-20261006-01/" in name or
                    "gap101-illegal-segment-store-old-image" in name or
                    "/results/gap71_qbs_fault/" in name for name in before["tests"]+[new]),
            "Known FAIL/timeout VDB in proposal")
    union = c.common.bitmap.combine(before, single)
    require(union["tests"] == before["tests"]+[new] and len(set(union["tests"])) == 720,
            "Not exact719 prefix plus successful AKVv2")
    return union, c.common.bitmap.delta(before, union)


def evaluate(base_seal):
    path = BASE / "admission-manifest.json"
    manifest = life.read_bound(path, base_seal)
    require(manifest["schema"] == "GAP102B_HISTORICAL719_ADMISSION_V1" and
            manifest["output"] == str(BASE), "Wrong formal719 admission")
    pins = {str(path): base_seal}
    def merge(values):
        nonlocal pins
        pins = life.merge_pins(pins, values)
    merge(manifest["output_pins"])
    require(all(Path(p).parent == BASE for p in manifest["output_pins"]), "Foreign baseline output")
    def read(path):
        require(str(path) in pins, "Unpinned input: "+str(path))
        return life.read_bound(path, pins[str(path)])
    state = read(BASE / "status.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            type(state["aggregate_passed"]) is int and state["aggregate_passed"] == 719 and
            state["baseline"] == 718 and state["new_passed"] == 1, "Wrong PASS719 status")
    merge(read(BASE / "evidence-pins.json"))
    parent_path = Path(manifest["baseline"]) / "admission-manifest.json"
    require(pins.get(str(parent_path)) == manifest["baseline_seal"], "Missing sealed718 parent")
    parent = read(parent_path)
    parent_bitmap_path = Path(manifest["baseline"]) / "combined-bits.json"
    require(pins.get(str(parent_bitmap_path)) == parent["output_pins"][str(parent_bitmap_path)],
            "Parent bitmap pin differs")
    before = read(BASE / "combined-bits.json")
    historical = read(parent_bitmap_path)
    require(before["tests"][:-1] == historical["tests"] and len(historical["tests"]) == 718,
            "Broken718->719 ancestry")
    require((BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(c.common.DESIGN), *before["tests"]], "719 ordered input ledger differs")
    merge({str(CANDIDATE / "candidate-seal.json"): CANDIDATE_SEAL})
    seal = read(CANDIDATE / "candidate-seal.json")
    require(seal["status"] == "NATIVE_OBSERVED_EVIDENCE_ONLY_NOT_ADMISSION" and
            seal["full_scalar_differential_qualified"] is False and
            not (CANDIDATE / "failure.json").exists(), "Rejected/unqualified candidate")
    require(all(Path(p).parent == CANDIDATE for p in seal["output_pins"]), "Foreign candidate output")
    merge(seal["input_pins"]); merge(seal["output_pins"])
    candidate_state = read(CANDIDATE / "status.json")
    require(candidate_state["status"] == "STRICT_AKV_NATIVE_CANDIDATE_NOT_ADMITTED" and
            candidate_state["coverage_admitted"] is False and
            candidate_state["full_scalar_differential_qualified"] is False, "Wrong candidate boundary")
    single = read(CANDIDATE / "sample-bits.json")
    for bitmap in (before, single):
        require(all(pins.get(p) == h for p,h in bitmap["input_hashes"].items()),
                "Missing metric input pins")
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_rebind_akv_column_boundary_719.py")):
        merge({str(path): life.digest(path)})
    life.check(pins)
    fresh = c.common.bitmap.collect(CANDIDATE / "sample-inputs.txt")
    require(fresh == single, "Actual successful VDB differs from sealed sample")
    union, delta = population(before, single)
    hits = []
    for bitmap in (before, single, union):
        record = bitmap["metrics"]["branch"][c.software.SCOPE]
        require(record["width"] == 166 and record["checksum"] == "131544421", "AKV shape differs")
        hits.append(bool(int(record["bits"], 16) & (1 << 141)))
    life.check(pins)
    return pins, union, delta, dict(status="AKV_NATIVE_ORACLE_VERIFIED_719_REBOUND_NOT_ADMITTED",
        baseline_tests=719, proposed_tests=720, exact719_prefix_preserved=True,
        raw24_baseline_hit=hits[0], raw24_sample_hit=hits[1], raw24_union_hit=hits[2],
        raw_delta=delta["metrics"], independent_native_command_VRF_CSR_oracle=True,
        full_scalar_differential_qualified=False, native_Spike_comparison=False,
        target_objective_met=hits[1], aggregate_admission_performed=False,
        official_DVE_report=False, simulations_started=False, rtl_changed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-seal", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins, union, delta, state = evaluate(args.baseline_seal)
    out.mkdir()
    for name, value in (("proposed-combined-bits.json", union), ("raw-delta.json", delta), ("status.json", state)):
        life.save(out / name, value)
    life.save(out / "proposal-seal.json", dict(input_pins=pins,
        output_pins={str(p):life.digest(p) for p in out.iterdir()}, coverage_admitted=False))
    print(json.dumps(dict(output=str(out), seal=life.digest(out / "proposal-seal.json"), result=state)))


if __name__ == "__main__":
    main()
