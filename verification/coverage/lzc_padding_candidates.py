#!/usr/bin/env python3
"""Bind LZC internal-OR structural evidence to diagnostic condition coordinates."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from lzc_padding_proof import SOURCE_SHA256, prove
from closure_point_inventory import read_xml, definition, points as shape_points

WIDTH_BY_CHECKSUM = {"3513283519": 10, "1372863097": 23}


def expected_expression(level, index):
    return (f"(gen_lzc.sel_nodes[(((2 ** ({level} + 1)) - 1) + ({index} * 2))] | "
            f"gen_lzc.sel_nodes[((((2 ** ({level} + 1)) - 1) + ({index} * 2)) + 1)])")


def shape_bindings(points, bitmap, database):
    for relative in ("design/verilog.design.xml", "shape/cond.verilog.shape.xml"):
        if hashlib.sha256((database / relative).read_bytes()).hexdigest() != bitmap["design"][relative]:
            raise ValueError("compiled condition design changed")
    design = read_xml(database / "design/verilog.design.xml")
    shape = read_xml(database / "shape/cond.verilog.shape.xml")
    instances = {n.get("id"): (n, d) for d in design.findall("srcdef") for n in d.findall("srcinst")}
    def scope_name(key, visited=()):
        if key in visited:
            raise ValueError("cyclic hierarchy")
        node, _ = instances[key]
        parent = node.get("pid")
        prefix = scope_name(parent, visited + (key,)) + "." if parent in instances else ""
        return prefix + node.get("name")
    hierarchy = {scope_name(key): module for key, (_, module) in instances.items()}
    result = {}
    selected = {p["scope"] for p in points if p.get("module") == "lzc"
                and p.get("metric") == "cond" and ".i_operand_queue_mfpu_" in p.get("scope", "")}
    for scope in selected:
        module = hierarchy[scope]
        if module.get("name") != "lzc":
            raise ValueError("scope not LZC in compiled hierarchy")
        record = bitmap["metrics"]["cond"][scope]
        node = definition(shape, module, record["checksum"])
        result[scope] = {p["raw_index"]: p for p in shape_points("cond", node, record["width"])}
        for point in result[scope].values():
            point["module_checksum"] = module.get("chksum")
    return result


def classify(points, bitmap, bindings):
    candidates, retained = [], []
    seen = set()
    for point in points:
        if (point.get("module") != "lzc" or point.get("metric") != "cond"
                or ".i_operand_queue_mfpu_" not in point.get("scope", "")):
            continue
        key = (point["scope"], int(point["raw_index"]))
        if key in seen:
            raise ValueError("duplicate coordinate")
        seen.add(key)
        record = bitmap["metrics"]["cond"][point["scope"]]
        bound = bindings[point["scope"]][key[1]]
        for field in ("raw_index", "native_id", "file_id", "line", "expression", "vector",
                      "attributes", "spec", "truth_table", "row"):
            if point.get(field) != bound.get(field):
                raise ValueError("compiled point identity mismatch: " + field)
        if str(record["checksum"]) != point["metric_checksum"]:
            raise ValueError("coverage checksum mismatch")
        index = key[1]
        bits = format(int(record["bits"], 16), f"0{record['width']}b")
        if len(bits) != record["width"] or not 0 <= index < record["width"]:
            raise ValueError("invalid coverage bit position")
        reason = "not an independently bound internal-OR condition"
        width = WIDTH_BY_CHECKSUM.get(point["metric_checksum"])
        spec = point.get("spec", {})
        attrs = point.get("attributes", {})
        table = point.get("truth_table", {})
        coords = re.fullmatch(r"level=(\d+),l=(\d+)", spec.get("generate_info", ""))
        eligible = (width is not None and coords is not None
                    and point.get("source_sha256") == SOURCE_SHA256
                    and point.get("line") == "93" and spec.get("lines") == "93"
                    and attrs.get("optype") == "13" and attrs.get("width") == "1"
                    and table == dict(ncols="2", nrows="3", vecs="000110"))
        node = None
        if eligible:
            level, number = map(int, coords.groups())
            eligible = (point["expression"] == expected_expression(level, number)
                        and attrs.get("exprstr") == point["expression"])
            node = next((n for n in prove(width)["nodes"]
                         if (n["level"], n["index"]) == (level, number)), None)
            eligible = eligible and node is not None
        vector = point.get("vector")
        if eligible:
            row = int(point["row"])
            if not 0 <= row < 3 or vector != table["vecs"][row * 2:row * 2 + 2]:
                raise ValueError("condition row/vector mismatch")
            if vector in node["unreachable_child_vectors"]:
                if bits[index] != "0":
                    raise ValueError("observed hit contradicts two-state structural proof")
                candidates.append(dict(point=point, structural_proof=node, width=width,
                                       module_checksum=bound.get("module_checksum"),
                                       qualification="CANDIDATE_ONLY_NATIVE_DVE_REVIEW_REQUIRED"))
                continue
            reason = "structurally reachable OR combination; retain even if unhit"
        retained.append(dict(point=point, hit=bits[index] == "1", reason=reason))
    return dict(status="DIAGNOSTIC_CANDIDATES_NOT_EXCLUSIONS", candidates=candidates,
                retained=retained, candidate_count=len(candidates), retained_count=len(retained),
                limitations=["native DVE vector ordering/leaf identity not yet independently qualified",
                             "two-state steady-state proof, not four-state initialization",
                             "non-OR and selector points remain included"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--bitmap", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--design-vdb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pins = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (args.inventory, args.bitmap, args.source)}
    if pins[str(args.source.resolve())] != SOURCE_SHA256:
        parser.error("source changed")
    inventory = json.loads(args.inventory.read_text())
    bitmap = json.loads(args.bitmap.read_text())
    database = args.design_vdb / "snps/coverage/db"
    bindings = shape_bindings(inventory["source_points"], bitmap, database)
    result = classify(inventory["source_points"], bitmap, bindings)
    result.update(input_sha256=pins, design=bitmap["design"], tests=bitmap["tests"])
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("status", "candidate_count", "retained_count")}))


if __name__ == "__main__":
    main()
