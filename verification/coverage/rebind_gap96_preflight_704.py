"""Rebind unchanged GAP96 Spike preflight to admitted raw704; no simulator."""
import argparse
import importlib.util
import json
from pathlib import Path

from build_gap96_preflight import OUT, sha, save, check, Design, points
from run_gap95_simulation import read_bound, merge_pins

PRE = OUT / "gap96-div32-pack-preflight-20261006-01"
PRE_SEAL = "f7f02db6bd6409f9fa7799903d2389f536415ea20a407afd260eda837df5c0b4"
BASE = OUT / "gap95-offline-admitted-20261006-01"
BITMAP_SEAL = "825a3cd9cbbe5824a856d83cba429bf8d537ba1f491b2f7c3db7ecfab973d1be"
STATUS_SEAL = "6d1161e685ccac4c54b53f6d7388d2c24919cba672e13e0c8b2ecc58ad4c090b"
# Same compiled metadata pinned by the independently reviewed FF1 config.
METADATA_PINS = {
    "shape/branch.verilog.info.xml": "e590433e98d78fd00a644dacba88e9fc67b8375f201e380ac7f06573cb15a7fd",
    "shape/tgl.verilog.info.xml": "5603b64b35df34925586b68ba6bf429c7e92836b239c94e9c193c666e3d70b0a",
    "shape/tgl.verilog.shape.xml": "243ae4d4d29b7ee2190ef35a39482f7287c78a260128315b666d500e90f18ae7",
}


def rebind_rows(original, bitmap, design):
    rows = []
    for row in original["rows"]:
        record = bitmap["metrics"]["branch"][row["scope"]]
        if (record["checksum"], record["width"]) != (row["checksum"], row["width"]):
            raise ValueError("Point shape changed")
        definition = design.definition(row["scope"], "branch")
        if definition.get("chksum") != row["checksum"]:
            raise ValueError("Compiled checksum changed")
        table = {p["raw_index"]: p for p in points("branch", definition, row["width"])}
        missing, now_hit = [], []
        for point in row["missing_points"]:
            if table.get(point["raw_index"]) != point:
                raise ValueError("Exact point identity changed")
            hit = bool(int(record["bits"], 16) & (1 << (record["width"] - point["raw_index"] - 1)))
            (now_hit if hit else missing).append(point)
        rows.append(dict(row, missing_points=missing, now_hit_since701=now_hit))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    if out.parent != OUT or out.resolve() != out or out.exists():
        raise ValueError("Fresh direct output required")
    prefile = PRE / "preflight-manifest.json"
    pre = read_bound(prefile, PRE_SEAL)
    if pre["status"] != "GAP96_SPIKE_PREFLIGHT_PASS_NOT_VCS" or pre["coverage_admitted"] is not False:
        raise ValueError("Original preflight is not qualified")
    pins = merge_pins({}, pre["pins"])
    pins = merge_pins(pins, {str(prefile): PRE_SEAL})
    check(pins)
    bitmapfile, statefile = BASE / "combined-bits.json", BASE / "status.json"
    bitmap, state = read_bound(bitmapfile, BITMAP_SEAL), read_bound(statefile, STATUS_SEAL)
    if (state["status"] != "PASS_RAW_UNION_HISTORICAL_ONLY" or state["aggregate_passed"] != 704 or
            state["new_passed"] != 3 or not len(bitmap["tests"]) == len(set(bitmap["tests"])) == 704):
        raise ValueError("Raw704 admission differs")
    if len(bitmap["tests"]) != 704 or any(r["status"] != "PASS" for r in state["cases"]):
        raise ValueError("Raw704 membership differs")
    evidencefile = BASE / "evidence-pins.json"
    pins = merge_pins(pins, json.loads(evidencefile.read_bytes()))
    for path in (evidencefile, BASE / "combined-inputs.txt", Path(__file__).resolve(),
                 OUT.parent / "coverage/test_rebind_gap96_preflight_704.py",
                 OUT.parent / "coverage/run_gap95_simulation.py"):
        pins = merge_pins(pins, {str(path): sha(path)})
    pins = merge_pins(pins, {str(bitmapfile): BITMAP_SEAL, str(statefile): STATUS_SEAL})
    design = Design(OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb")
    pins = merge_pins(pins, {str(design.db / name): expected for name, expected in METADATA_PINS.items()})
    check(pins)
    old = json.loads((OUT / "gap94-offline-admitted-701-20261006-01/combined-bits.json").read_bytes())
    if bitmap["design"] != old["design"] or bitmap["tests"][:701] != old["tests"]:
        raise ValueError("Raw704 baseline/design differs")
    if (BASE / "combined-inputs.txt").read_text().splitlines() != [str(design.db.parents[2]), *bitmap["tests"]]:
        raise ValueError("Input population differs")
    for relative, expected in bitmap["design"].items():
        path = design.db / relative
        if sha(path) != expected:
            raise ValueError("Compiled design drift")
        pins = merge_pins(pins, {str(path): expected})
    original = json.loads((PRE / "target-before.json").read_bytes())
    review_path = OUT / "gap56-operand-independent-review-20261004-01/review.py"
    module_spec = importlib.util.spec_from_file_location("gap96_704_compiled_parameters", review_path)
    review = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(review)
    for row in original["rows"]:
        if review.signature(design.definition(row["wrapper"], "tgl")) != [row["compiled_parameters"]]:
            raise ValueError("Compiled wrapper parameters changed")
    rows = rebind_rows(original, bitmap, design)
    count = sum(len(r["missing_points"]) for r in rows)
    check(pins)
    out.mkdir()
    save(out / "target-before.json", dict(original, status="GAP96_RAW704_TARGETS_NOT_MEASURED",
         baseline_tests=704, target_unhit_count=count, rows=rows))
    pins[str(out / "target-before.json")] = sha(out / "target-before.json")
    save(out / "preflight-manifest.json", dict(status="GAP96_SPIKE_PREFLIGHT_REBOUND_RAW704_NOT_VCS",
         case=pre["case"], eew=pre["eew"], vl=pre["vl"], checks=pre["checks"], symbols=pre["symbols"],
         expected_vector_instructions=pre["expected_vector_instructions"],
         expected_vector_bytes=pre["expected_vector_bytes"], baseline_tests=704,
         target_unhit_count=count, original_preflight=str(prefile), original_preflight_seal=PRE_SEAL,
         input_elf=str(PRE / "input.elf"), input_spike_trace=str(PRE / "spike.trace"),
         pins=pins, measured_raw_increment=None, coverage_admitted=False, rtl_changed=False))
    print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"),
                         baseline_tests=704, target_unhit_count=count)))


if __name__ == "__main__":
    main()
