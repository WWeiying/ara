#!/usr/bin/env python3
"""Offline VCS XML gap analysis. Never invokes a simulator, DVE or URG.

Raw positions are NOT DVE scoring units. Source coordinates/checksums come from
the frozen design. Line uses explicit basic-block indices. Other per-point
layouts are explicitly marked inferred, even when their total lengths agree.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

METRICS = ("line", "branch", "cond", "fsm")
FOCUS = {"operand_queue", "operand_requester", "vmfpu", "ara_dispatcher", "acc_dispatcher"}
TAGS = {"line": "linedef", "branch": "branch_def", "cond": "conddef", "fsm": "fsmdef"}
LIMITS = [
    "Raw bit positions are not source-line/branch/condition/FSM scoring denominators.",
    "A zero OR bit means no selected sample set that raw position; not proof of architectural unreachability or a bug.",
    "Line maps explicit linebb@index to a left-to-right raw position; bit orientation is a format interpretation, not vendor-API validation.",
    "Branch spec/vector concatenation, condition condregid/truth-table concatenation and FSM state/transition concatenation are inferred layouts.",
    "Inferred point rows are candidates only, never confirmed individual missing outcomes; unsupported layouts are withheld.",
    "line_ignore, multiple statements per basic block, generated/parameter-disabled paths and synthetic positions change scoring.",
    "Repeated lanes/queues are separate raw instances; summed totals are not deduplicated module-definition coverage.",
    "No DVE/URG invocation, exclusion creation, oracle rerun, RTL change, or claim of assertion coverage.",
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Reader:
    def __init__(self):
        self.pins = {}

    def bytes(self, path, expected=None):
        path = Path(path).resolve(strict=True)
        data = path.read_bytes()
        actual = digest(data)
        if expected is not None and actual != expected:
            raise ValueError(f"hash mismatch: {path}")
        if str(path) in self.pins and self.pins[str(path)] != actual:
            raise ValueError(f"changed during analysis: {path}")
        self.pins[str(path)] = actual
        return data

    def json(self, path, expected=None):
        return json.loads(self.bytes(path, expected))

    def xml(self, path, expected=None):
        data = self.bytes(path, expected)
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)  # Includes trailer/CRC validation.
        return ET.fromstring(data)


def sample_map(collection):
    result = {}
    for sample in collection["samples"]:
        if sample.get("status") != "PASS" or sample.get("passed_only") is not True or not sample.get("vdb_valid"):
            raise ValueError("analysis accepts independently passed, valid-VDB samples only")
        key = str(Path(sample["vdb"]).resolve(strict=True))
        if key in result:
            raise ValueError("duplicate VDB in collection")
        result[key] = sample
    return result


def hierarchy(design):
    definitions = {e.get("id"): e.get("name") for e in design.findall("srcdef")}
    nodes = {e.get("id"): (e.attrib, d.get("name")) for d in design.findall("srcdef") for e in d.findall("srcinst")}
    paths = {}
    def full(key, stack=()):
        if key in stack:
            raise ValueError("cyclic design hierarchy")
        if key not in paths:
            node, _ = nodes[key]
            parent = node["pid"]
            paths[key] = (full(parent, stack + (key,)) + "." if parent in nodes else "") + node["name"]
        return paths[key]
    return {full(key): module for key, (_, module) in nodes.items()}, definitions


def data_rows(root):
    rows = {}
    for element in root.findall("instance_data"):
        name, value = element.get("name"), element.get("value", "")
        if name in rows or set(value) - {"0", "1"}:
            raise ValueError("duplicate instance or nonbinary data encoding")
        rows[name] = (value, element.get("chksum"))
    return rows


def aggregate(reader, samples, baseline, metric):
    universe, merged, initial = None, {}, {}
    for directory, sample in samples.items():
        path = Path(directory) / "snps/coverage/db/testdata" / sample["coverage_test"] / f"{metric}.verilog.data.xml"
        rows = data_rows(reader.xml(path, sample["vdb_files"][str(path)]))
        shape = {name: (len(value), checksum) for name, (value, checksum) in rows.items()}
        if universe is None:
            universe = shape
        if shape != universe:
            raise ValueError(f"{metric} point universe/checksum differs: {directory}")
        if directory in baseline and baseline[directory]["vdb_files"][str(path)] != sample["vdb_files"][str(path)]:
            raise ValueError("baseline sample hash differs")
        for name, (value, _) in rows.items():
            bits = int(value or "0", 2)
            merged[name] = merged.get(name, 0) | bits
            if directory in baseline:
                initial[name] = initial.get(name, 0) | bits
    return universe, merged, initial


def bit_at(bits, length, index):
    if not 0 <= index < length:
        raise ValueError("shape index outside bitmap")
    return bool(bits & (1 << (length - index - 1)))


def point_layout(metric, definition, length):
    """Return source-bearing points and a confidence tag; never infer silently."""
    points = []
    if metric == "line":
        for process in definition.iter("lineprocess"):
            for bb in process.findall("linebb"):
                index = int(bb.get("index"))
                points.append({"offset": index, "kind": "basic_block", "file_id": bb.get("file_id"),
                    "line": bb.get("line_num"), "expression": bb.get("bbsig", ""),
                    "ignore": bb.get("line_ignore"), "generate": process.get("generate_info"),
                    "statements": [s.attrib for s in bb.findall("linestmt")]})
        indices = [p["offset"] for p in points]
        if not indices or len(set(indices)) != len(indices) or max(indices) + 1 != length:
            return [], "UNSUPPORTED_LINE_INDEX_LAYOUT"
        return points, "EXPLICIT_LINEBB_INDEX_BIT_ORDER_NOT_VENDOR_VALIDATED"
    if metric == "branch":
        for spec in definition.iter("branch_spec"):
            vectors = spec.findall("branch_vector")
            if len(vectors) != int(spec.get("totalbranches", "-1")):
                return [], "UNSUPPORTED_BRANCH_VECTOR_COUNT"
            expressions = [e.attrib for e in spec if e.tag in ("branch_expr", "branch_cexpr")]
            for vector in vectors:
                points.append({"offset": len(points), "kind": "branch_vector", "file_id": spec.get("file_id"),
                    "line": expressions[0].get("id") if expressions else None,
                    "expression": " ; ".join(e.get("exprstr", "") for e in expressions),
                    "spec_id": spec.get("id"), "vector": vector.get("vector"),
                    "ignore": spec.get("skip_annotation"), "expressions": expressions})
        confidence = "INFERRED_BRANCH_SPEC_VECTOR_ORDER"
    elif metric == "cond":
        expressions = []
        for spec in definition.iter("condspec"):
            expressions += [(int(e.get("condregid")), e, spec) for e in spec.iter("expr_monitored")]
        ids = [i for i, _, _ in expressions]
        if len(ids) != len(set(ids)):
            return [], "UNSUPPORTED_CONDITION_REG_IDS"
        for _, expr, spec in sorted(expressions, key=lambda row: row[0]):
            table = expr.find("truth_table")
            if table is None:
                return [], "UNSUPPORTED_CONDITION_TABLE"
            count, width = int(table.get("nrows")), int(table.get("ncols"))
            vectors = table.get("vecs", "")
            if len(vectors) != count * width:
                return [], "UNSUPPORTED_CONDITION_TABLE_WIDTH"
            for row in range(count):
                points.append({"offset": len(points), "kind": "condition_table_row", "file_id": spec.get("file"),
                    "line": spec.get("lines"), "expression": expr.get("exprstr"), "reg_id": expr.get("condregid"),
                    "vector": vectors[row * width:(row + 1) * width], "generate": spec.get("generate_info")})
        confidence = "INFERRED_CONDREGID_TRUTH_TABLE_ORDER"
    else:
        for machine in definition.iter("fsmfsm"):
            states = {s.get("id"): s for s in machine.findall("state")}
            for state in machine.findall("state"):
                points.append({"offset": len(points), "kind": "fsm_state", "file_id": definition.get("file"),
                    "line": state.get("line"), "expression": state.get("name"), "fsm": machine.get("name"),
                    "state_id": state.get("id"), "flag": state.get("flag")})
            for transition in machine.findall("transition"):
                points.append({"offset": len(points), "kind": "fsm_transition", "file_id": definition.get("file"),
                    "line": transition.get("line"), "fsm": machine.get("name"), "flag": transition.get("flag"),
                    "expression": states[transition.get("fromid")].get("name") + " -> " + states[transition.get("toid")].get("name")})
        confidence = "INFERRED_FSM_STATES_THEN_TRANSITIONS_ORDER"
    if len(points) != length:
        return [], f"UNSUPPORTED_{metric.upper()}_LENGTH_shape{len(points)}_raw{length}"
    return points, confidence


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["empty"])
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reader = Reader()
    collection = reader.json(args.collection)
    baseline_collection = reader.json(args.baseline) if args.baseline else None
    samples = sample_map(collection)
    baseline = sample_map(baseline_collection) if baseline_collection else {}
    if args.expect_samples and len(samples) != args.expect_samples:
        raise ValueError("unexpected sample count")
    if not samples or not set(baseline) <= set(samples):
        raise ValueError("baseline is not a subset of current selected samples")
    if baseline_collection and baseline_collection["image"] != collection["image"]:
        raise ValueError("different images cannot define an increment")
    for path, checksum in collection["image"].items():
        reader.bytes(path, checksum)
    manifest = reader.json(args.source_manifest)
    source_hashes = {r["path"]: r["sha256"] for r in manifest["files"]}
    # Hash the frozen source set once, not for each sample/metric.
    for path, checksum in source_hashes.items():
        reader.bytes(path, checksum)
    db = args.design_vdb.resolve() / "snps/coverage/db"
    design_pins_path = args.collection.resolve().parent.parent / "passed-only.inputs.before.json"
    design_pins = reader.json(design_pins_path)[str(args.design_vdb.resolve())]
    for path, expected in design_pins.items():
        reader.bytes(path, expected)
    modules, defnames = hierarchy(reader.xml(db / "design/verilog.design.xml"))
    files = {e.get("id"): e.get("name") for e in reader.xml(db / "auxiliary/verilog.sourceinfo.xml").findall("fileinfo")}
    parameters = defaultdict(dict)
    for line in reader.bytes(db / "auxiliary/verilog.instance_parameters.txt").decode().splitlines():
        if "\x01" in line:
            name, value = line.split("\x01", 1)
            instance, _, key = name.rpartition(".")
            if modules.get(instance) in FOCUS:
                parameters[instance][key] = value
    for sample in samples.values():
        audits = [p for p in sample["files"] if p.endswith("/independent_audit.json")]
        if not audits:
            raise ValueError("sample lacks an independent audit reference")
        for path in audits:
            audit = reader.json(path, sample["files"][path])
            if audit.get("status") != "PASS" or audit.get("errors"):
                raise ValueError("referenced audit is not PASS")
    module_rows, instance_rows, layout_checks, point_groups = [], [], [], {}
    top_raw = {}
    raw_universes = {}
    for metric in METRICS:
        print(f"Reading {metric}: {len(samples)} PASS samples", flush=True)
        universe, merged, initial = aggregate(reader, samples, baseline, metric)
        raw_universes[metric] = {"instances": len(universe), "sha256": digest(json.dumps(universe, sort_keys=True).encode())}
        shape = reader.xml(db / "shape" / f"{metric}.verilog.shape.xml")
        definitions = defaultdict(list)
        for d in shape.findall(TAGS[metric]):
            definitions[d.get("chksum")].append(d)
        grouped = defaultdict(lambda: Counter())
        top = Counter()
        cache = {}
        for instance, (length, checksum) in universe.items():
            bits, before = merged[instance], initial.get(instance, 0)
            hit, old_hit = bin(bits).count("1"), bin(before).count("1")
            module = modules.get(instance, "UNMAPPED")
            if instance == "ara_tb" or instance.startswith("ara_tb."):
                top.update(bits=length, hit=hit, baseline_hit=old_hit)
            if not instance.startswith(args.scope):
                continue
            values = {"instances": 1, "raw_bits": length, "raw_hit": hit,
                      "raw_zero": length - hit, "new_raw_hits": hit - old_hit}
            grouped[module].update(values)
            instance_rows.append(dict(metric=metric, module=module, instance=instance, **values))
            if module not in FOCUS or not length:
                continue
            key = (checksum, length)
            if key not in cache:
                defs = definitions.get(checksum, [])
                candidates = [point_layout(metric, d, length) for d in defs]
                if not candidates or any(c != candidates[0] for c in candidates[1:]):
                    cache[key] = ([], "MISSING_OR_AMBIGUOUS_SHAPE_CHECKSUM")
                else:
                    cache[key] = candidates[0]
            points, confidence = cache[key]
            layout_checks.append({"metric": metric, "module": module, "instance": instance,
                                  "raw_length": length, "shape_checksum": checksum, "mapping": confidence,
                                  "mapped_positions": len(points), "unmapped_positions": length - len(points)})
            for point in points:
                path = files.get(point["file_id"])
                record = dict(point, metric=metric, module=module, shape_checksum=checksum,
                              mapping=confidence, source=path, source_hash_verified=path in source_hashes)
                groupkey = json.dumps(record, sort_keys=True)
                if groupkey not in point_groups:
                    point_groups[groupkey] = dict(record, hit_instances=[], zero_instances=[], newly_hit_instances=[])
                group = point_groups[groupkey]
                hit_now = bit_at(bits, length, point["offset"])
                group["hit_instances" if hit_now else "zero_instances"].append(instance)
                if hit_now and not bit_at(before, length, point["offset"]):
                    group["newly_hit_instances"].append(instance)
        for module, values in grouped.items():
            module_rows.append(dict(metric=metric, module=module, **dict(values)))
        top_raw[metric] = dict(top, raw_percent=100 * top["hit"] / top["bits"] if top["bits"] else None)
    points = list(point_groups.values())
    source_text = {}
    for point in points:
        path, line = point["source"], point["line"]
        if point["source_hash_verified"] and line and str(line).isdigit():
            if path not in source_text:
                source_text[path] = Path(path).read_text().splitlines()
            lines, number = source_text[path], int(line)
            point["source_excerpt"] = "\n".join(f"{i+1}: {lines[i]}" for i in range(max(0, number-2), min(len(lines), number+2)))
    module_rows.sort(key=lambda r: (r["metric"], -r["raw_zero"], r["module"]))
    write_csv(out / "modules.csv", module_rows)
    write_csv(out / "instances.csv", instance_rows)
    with (out / "focus_points.jsonl").open("w") as stream:
        for point in points:
            stream.write(json.dumps(point, sort_keys=True) + "\n")
    write_json(out / "layout_checks.json", layout_checks)
    write_json(out / "instance_parameters.json", parameters)
    dve = []
    summary_path = args.collection.resolve().parent / "summary.csv"
    if summary_path.is_file():
        dve = list(csv.DictReader(io.StringIO(reader.bytes(summary_path, collection["reports"][str(summary_path)]).decode())))
    summary = {"status": "ANALYZED_NOT_SIGNOFF", "samples": len(samples), "baseline_samples": len(baseline),
               "scope": args.scope, "raw_top": top_raw, "existing_dve_summary": dve, "raw_universes": raw_universes,
               "module_focus": [r for r in module_rows if r["module"] in FOCUS],
               "mapping_counts": dict(Counter(r["mapping"] for r in layout_checks)), "limitations": LIMITS,
               "point_rows": len(points), "point_rows_with_any_zero_instance": sum(bool(p["zero_instances"]) for p in points)}
    write_json(out / "summary.json", summary)
    # A final hash sweep ensures analysis did not observe a changing collection.
    for path, expected in list(reader.pins.items()):
        reader.bytes(path, expected)
    reader.bytes(Path(__file__))
    write_json(out / "provenance.json", {"argv": sys.argv, "input_sha256": reader.pins,
               "collection": str(args.collection.resolve()), "baseline": str(args.baseline.resolve()) if args.baseline else None,
               "image": collection["image"], "source_manifest": str(args.source_manifest.resolve())})
    text = ["# Offline VCS Coverage Gap Analysis", "", f"PASS samples: {len(samples)}; same-image baseline: {len(baseline)}.",
            "", "No tools or simulations were launched. All consumed raw XML hashes and source hashes were checked.",
            "", "## Focus Raw Distribution", "", "|Metric|Module|Raw zero/total|New raw hits|", "|---|---|---:|---:|"]
    for row in summary["module_focus"]:
        text.append(f"|{row['metric']}|{row['module']}|{row['raw_zero']}/{row['raw_bits']}|{row['new_raw_hits']}|")
    text += ["", "## Mapping and Limits", "", *["- " + s for s in LIMITS], "", "## Outputs", "",
             "- modules.csv / instances.csv: raw counts, scoped below the SoC instance.",
             "- focus_points.jsonl: explicit-index line points and clearly marked candidate layouts; includes hit/zero instance lists and RTL excerpts.",
             "- layout_checks.json: checksum/length guard results, including withheld mappings.",
             "- instance_parameters.json: elaborated capabilities to review before labeling a zero as missing stimulus.",
             "- summary.json / provenance.json: DVE comparison, same-image increment, complete consumed-file hashes."]
    (out / "README.md").write_text("\n".join(text) + "\n")
    print(f"ANALYZED_NOT_SIGNOFF: {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--design-vdb", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--scope", default="ara_tb.dut.i_ara_soc.")
    parser.add_argument("--expect-samples", type=int)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
