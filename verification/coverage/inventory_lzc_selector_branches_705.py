"""Source-bound padded LZC branch candidates; no native mapping or waiver."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import points
from lzc_padding_proof import prove, SOURCE_SHA256
from lzc_selector_candidates import selector_expression

OUT = ROOT / "verification/out"


def structural_node(point, width):
    if point["line"] != "95":
        return None
    match = re.fullmatch(r"level=(\d+),l=(\d+)", point["attributes"].get("generate_info", ""))
    if match is None:
        raise ValueError("Missing generate coordinates")
    level, index = map(int, match.groups())
    if point["expression"] != selector_expression(level, index):
        raise ValueError("Selector expression differs")
    if point["attributes"].get("totalbranches") != "2":
        raise ValueError("Not a two-arm selector")
    node = next((n for n in prove(width)["nodes"] if (n["level"], n["index"]) == (level, index)), None)
    if node is None:
        raise ValueError("Not an internal LZC node")
    return node if not node["left_real_bits"] else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.absolute()
    if output.parent != OUT or output.exists():
        raise ValueError("Fresh direct output required")
    pins = {}

    def pin(path, expected=None):
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected is not None and value != expected:
            raise ValueError("Input drift: " + str(path))
        if str(path) in pins and pins[str(path)] != value:
            raise ValueError("Conflicting pin")
        pins[str(path)] = value

    base = OUT / "gap96-offline-admitted-705-20261006-01"
    for path in (base / "combined-bits.json", base / "status.json"):
        pin(path)
    bitmap = json.loads((base / "combined-bits.json").read_bytes())
    state = json.loads((base / "status.json").read_bytes())
    if state["status"] != "PASS_RAW_UNION_HISTORICAL_ONLY" or state["aggregate_passed"] != 705:
        raise ValueError("Not admitted705")
    if len(bitmap["tests"]) != len(set(bitmap["tests"])) or len(bitmap["tests"]) != 705:
        raise ValueError("Wrong population")
    source = ROOT / "hardware/deps/common_cells/src/lzc.sv"
    pin(source, SOURCE_SHA256)
    build = OUT / "repaired-aligned-build-20260930-01/build-source-pins.json"
    pin(build)
    if json.loads(build.read_bytes())[str(source)] != SOURCE_SHA256:
        raise ValueError("LZC source not old-image source")
    design = Design(OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb")
    for relative, expected in bitmap["design"].items():
        pin(design.db / relative, expected)
    review_path = OUT / "gap56-operand-independent-review-20261004-01/review.py"
    pin(review_path)
    spec = importlib.util.spec_from_file_location("lzc705_parameters", review_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    rows, retained = [], 0
    for scope, record in bitmap["metrics"]["branch"].items():
        if ".i_operand_queue_mfpu_" not in scope or record["checksum"] is None:
            continue
        if design.source(scope)["resolved_path"] != str(source):
            continue
        parameters = review.signature(design.definition(scope, "tgl"))
        if len(parameters) != 1 or parameters[0].get("WIDTH") not in (10, 23) or parameters[0].get("MODE") != 1:
            raise ValueError("Compiled LZC parameter scope differs")
        width = parameters[0]["WIDTH"]
        definition = design.definition(scope, "branch")
        if definition.get("chksum") != record["checksum"]:
            raise ValueError("Compiled branch ownership differs")
        for point in points("branch", definition, record["width"]):
            if point["line"] != "95":
                continue
            hit = bool(int(record["bits"], 16) & (1 << (record["width"] - 1 - point["raw_index"])))
            node = structural_node(point, width)
            if node is not None and not hit:
                rows.append(dict(scope=scope, point=point, parameters=parameters[0],
                    metric_checksum=record["checksum"], proof=node, unreachable_selector_value=1,
                    decision="CANDIDATE_NATIVE_ARM_IDENTITY_REQUIRED", native_qualified=False))
            else:
                retained += 1
    if len(rows) != 60:
        raise ValueError("Unexpected padded selector candidate count")
    for name in (__file__, "lzc_padding_proof.py", "lzc_selector_candidates.py",
                 "closure_point_inventory.py", "inventory_operand_debug.py"):
        path = Path(name)
        pin(path.resolve() if path.is_absolute() else Path(__file__).resolve().parent / path)
    for path, expected in pins.items():
        pin(Path(path), expected)
    result = dict(status="LZC705_BRANCH_STRUCTURE_ONLY_NOT_EXCLUSIONS", tests=705,
                  candidate_count=len(rows), retained_positions=retained, rows=rows, pins=pins,
                  native_qualified=False, exclusions_applied=False,
                  assumptions=["normal two-state operation", "MODE only permutes input bits"],
                  limitations=["raw/native branch vector does not yet identify true arm independently",
                               "no four-state initialization proof"])
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "candidate_count", "retained_positions")}))


if __name__ == "__main__":
    main()
