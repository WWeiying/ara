#!/usr/bin/env python3
"""Read-only branch/FSM union with explicit design checksum inheritance."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "frozen_points", ROOT / "verification/coverage/vcs_point_audit.py")
FROZEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FROZEN)


def xml(path):
    with gzip.open(path, "rb") as stream:
        return ET.parse(stream).getroot()


def audit(inputs, cache_path):
    paths = [Path(p) for p in inputs.read_text().splitlines() if p.strip()]
    assert len(paths) > 1 and len(paths) == len(set(paths))
    cache = json.loads(cache_path.read_text())
    assert cache["tests"] == list(map(str, paths[1:]))
    shape_dir = paths[0] / "snps/coverage/db/shape"
    record = {"inputs": str(inputs.resolve()), "tests": len(paths) - 1, "instances": {},
              "limits": "Raw bits, not DVE scoring units; branch vectors reversed within each spec, "
                        "cross-checked against explicit datapath linebb indices. FSM order inferred. "
                        "Line uses explicit linebb indices. Gains require same-image passing VCS runs."}
    record["cache"] = str(cache_path.resolve())
    record["cache_sha256"] = hashlib.sha256(cache_path.read_bytes()).hexdigest()
    design = xml(shape_dir.parent / "design/verilog.design.xml")
    nodes = {n.get("id"): (n, d.get("id")) for d in design.iter("srcdef")
             for n in d.findall("srcinst")}
    def full(key):
        node = nodes[key][0]
        return (full(node.get("pid")) + "." if node.get("pid") in nodes else "") + node.get("name")
    hierarchy = {full(key): definition for key, (_, definition) in nodes.items()}
    pins = json.loads((paths[0].parents[1] / "build-source-pins.json").read_text())
    record["source_pins"] = {}
    for relative in ("hardware/src/lane/operand_queue.sv", "hardware/src/lane/operand_queues_stage.sv",
                     "hardware/src/lane/lane_sequencer.sv", "hardware/src/masku/masku.sv",
                     "hardware/src/sldu/sldu.sv", "hardware/src/sldu/sldu_op_dp.sv",
                     "hardware/src/ara_dispatcher.sv"):
        path = ROOT / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert pins[str(path)] == digest, path
        record["source_pins"][relative] = digest
    pattern = re.compile(r"\.(i_dispatcher|i_masku|i_masku_operands|i_sldu|i_sldu_op_dp|"
                         r"i_p2_stride_gen|i_operand_queue_[a-z_]+)$")
    for metric in ("branch", "fsm", "line"):
        shape = xml(shape_dir / f"{metric}.verilog.shape.xml")
        tag = {"branch": "branch_def", "line": "linedef", "fsm": "fsmdef"}[metric]
        if metric != "fsm":
            defaults = {d.get("id"): d.get("chksum") for d in shape.iter(tag)}
            checksums = {name: defaults[d] for name, d in hierarchy.items() if d in defaults}
            info = xml(shape_dir / f"{metric}.verilog.info.xml")
            checksums.update({n.get("name"): n.get("chksum") for n in info.iter("instance_data")})
        else:
            checksums = {n.get("name"): d.get("chksum")
                         for d in shape.iter("fsmdef") for n in d.iter("fsminst")}
        selected = {n: c for n, c in checksums.items() if pattern.search(n)}
        definitions = {d.get("chksum"): d for d in shape.iter(tag)}
        decoded = {}
        for name, checksum in selected.items():
            definition = definitions[checksum]
            if metric == "line":
                rows = [dict(bb.attrib, statements=[s.attrib for s in bb.findall("linestmt")])
                        for bb in definition.iter("linebb")]
                rows.sort(key=lambda row: int(row["index"]))
                assert len({r["index"] for r in rows}) == len(rows), name
                decoded[name] = [{"index": str(i), "unmapped": True}
                                 for i in range(int(rows[-1]["index"]) + 1)]
                for row in rows:
                    decoded[name][int(row["index"])] = row
            else:
                decoded[name] = FROZEN.points(shape, metric, checksum)
                if metric == "branch":
                    specs = {s.get("id"): s for s in definition.iter("branch_spec")}
                    decoded[name] = [p for spec in specs for p in reversed(
                        [p for p in decoded[name] if p["spec"] == spec])]
                    for point in decoded[name]:
                        point["case_items"] = [c.attrib for c in specs[point["spec"]].iter("branch_citem")]
        for name in selected:
            cached = cache["metrics"][metric][name]
            assert cached["checksum"] in (None, selected[name]), name
            assert cached["width"] == len(decoded[name]), name
            bits = format(int(cached["bits"], 16), f"0{cached['width']}b")
            assert len(bits) == cached["width"]
            record["instances"].setdefault(name, {})[metric] = {
                "checksum": selected[name], "total": len(bits), "covered": bits.count("1"),
                "bits": bits, "checksum_inherited": cached["checksum"] is None,
                "missing": [dict(p, bit_index=i) for i, p in enumerate(decoded[name]) if bits[i] == "0"]}
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inputs, args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for name, metrics in result["instances"].items():
        print(name, {m: f"{v['covered']}/{v['total']}" for m, v in metrics.items()})
