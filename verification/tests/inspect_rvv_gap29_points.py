#!/usr/bin/env python3
"""Offline original-473 raw line-bin inspection; no VCS/DVE invocation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import analyze_vcs_gaps as gap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    parent = root / "verification/out/vcs-memory-gap-20260928-01"
    reader = gap.Reader()
    collection = reader.json(parent / "collection.json")
    plan = reader.json(parent / "plan.json")
    samples = gap.sample_map({"samples": collection["cases"]})
    if len(samples) != 473:
        raise ValueError("expected original 473 PASS set")
    universe, merged, _ = gap.aggregate(reader, samples, {}, "line")
    db = Path(plan["design_vdb"]) / "snps/coverage/db"
    shape = reader.xml(db / "shape/line.verilog.shape.xml",
                       plan["design_files"][str(db / "shape/line.verilog.shape.xml")])
    definitions = {}
    for definition in shape.findall("linedef"):
        definitions.setdefault(definition.get("chksum"), []).append(definition)
    focus = ("i_vmfpu", "i_vldu", "i_dispatcher", "i_operand_queue_mfpu_a",
             "i_operand_queue_mfpu_b", "i_operand_queue_mfpu_c")
    report = []
    for instance, (length, checksum) in universe.items():
        if not instance.endswith(focus):
            continue
        candidates = [gap.point_layout("line", d, length) for d in definitions[checksum]]
        if any(c != candidates[0] for c in candidates):
            raise ValueError("ambiguous point shape")
        points, confidence = candidates[0]
        zero = [p for p in points if not gap.bit_at(merged[instance], length, p["offset"])]
        report.append({"instance": instance, "mapping": confidence,
                       "raw_zero": len(zero), "points": zero})
        useful = [p for p in zero if p["expression"] and
                  not p["expression"].startswith(("$display", ";", "illegal_insn"))]
        print(instance, "raw_zero", len(zero), "candidate-lines",
              sorted({int(p["line"]) for p in useful if p["line"]}))
    record = {"status": "ANALYZED", "passed": 473, "metric": "line", "limits": gap.LIMITS,
              "instances": report, "files": reader.pins,
              "note": "candidate raw bins, not vendor-validated point scores or reachability"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
