#!/usr/bin/env python3
"""Map the shared baseline bitmap cache onto frozen decoder shapes, read-only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/coverage"))
import analyze_vcs_gaps as gap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / "verification/out/"
                        "gap34-current-20261001-01/combined-dve/inputs.txt")
    parser.add_argument("--cache", type=Path, default=ROOT / "verification/out/"
                        "gap35-analysis-20261004-01/baseline-bits.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reader = gap.Reader()
    paths = [Path(p) for p in reader.bytes(args.inputs).decode().splitlines() if p]
    if len(paths) != 621 or len(set(paths)) != len(paths):
        raise ValueError("expected design plus 620 unique baseline test VDBs")
    cache = reader.json(args.cache)
    if cache["tests"] != [str(p) for p in paths[1:]]:
        raise ValueError("cache membership differs from baseline inputs")
    db = paths[0] / "snps/coverage/db"
    modules, _ = gap.hierarchy(reader.xml(db / "design/verilog.design.xml",
                              cache["design"]["design/verilog.design.xml"]))
    focus = {name for name, module in modules.items()
             if module in ("compressed_decoder", "decoder")}
    files = {e.get("id"): e.get("name") for e in
             reader.xml(db / "auxiliary/verilog.sourceinfo.xml").findall("fileinfo")}
    reports = []
    for metric in ("line", "branch"):
        shape_path = f"shape/{metric}.verilog.shape.xml"
        definitions = reader.xml(db / shape_path, cache["design"][shape_path])
        for name in sorted(focus):
            row = cache["metrics"][metric][name]
            length, checksum = row["width"], row["checksum"]
            bits = int(row["bits"], 16)
            if bits < 0 or bits.bit_length() > length:
                raise ValueError("invalid cached bitmap")
            candidates = [gap.point_layout(metric, d, length) for d in
                          definitions.findall(gap.TAGS[metric])
                          if d.get("chksum") == checksum]
            if not candidates or any(c != candidates[0] for c in candidates):
                raise ValueError(f"ambiguous shape: {name}")
            points, confidence = candidates[0]
            specs = {}
            for point in points:
                point["source"] = files.get(point["file_id"])
                point["hit"] = gap.bit_at(bits, length, point["offset"])
                if metric == "branch":
                    specs[point["spec_id"]] = point.pop("expressions")
                    point.pop("expression")
            reports.append(dict(instance=name, module=modules[name], metric=metric,
                                mapping=confidence, raw_length=length, points=points,
                                branch_expressions=specs))
            print(metric, name, confidence, "zero", sum(not p["hit"] for p in points))
            if metric == "line":
                print("zero lines:", sorted({int(p["line"]) for p in points
                                             if not p["hit"] and p["line"]}))
    with args.output.open("x") as stream:
        json.dump(dict(samples=620, limits=gap.LIMITS, instances=reports,
                       files=reader.pins, cache=str(args.cache)), stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
