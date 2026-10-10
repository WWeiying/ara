#!/usr/bin/env python3
"""Read-only raw VCS bitmap audit. Does not invoke any vendor tool."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/coverage"))
from analyze_vcs_gaps import LIMITS, TAGS, point_layout


def selected(name):
    return any(part in name for part in (".i_qbs_engine", ".i_akv_engine")) and (
        name.count(".") <= 8 and "gen_" not in name and "i_fpnew" not in name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / "verification/out/gap34-current-20261001-01/combined-dve/inputs.txt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [Path(p) for p in args.inputs.read_text().splitlines() if p.strip()]
    if len(paths) != len(set(paths)) or len(paths) < 2:
        raise ValueError("expected distinct design and sample VDBs")
    report = {"inputs": str(args.inputs.resolve()), "tests": len(paths) - 1,
              "limits": LIMITS, "files": {}, "instances": {}}

    def xml(path):
        data = path.read_bytes()
        report["files"][str(path)] = hashlib.sha256(data).hexdigest()
        return ET.fromstring(gzip.decompress(data))

    for metric, tag in TAGS.items():
        merged, checksums, widths = {}, {}, {}
        for test_index, test in enumerate(paths[1:]):
            files = list(test.glob(f"snps/coverage/db/testdata/*/{metric}.verilog.data.xml"))
            if len(files) != 1:
                raise ValueError(f"ambiguous metric: {test}")
            root = xml(files[0])
            inherited = None
            found = set()
            for node in root.iter("instance_data"):
                # VCS omits a repeated checksum on subsequent instances of a definition.
                inherited = node.get("chksum", inherited)
                name, value = node.get("name"), node.get("value", "")
                if not selected(name) or not value:
                    continue
                found.add(name)
                if set(value) - {"0", "1"} or inherited is None:
                    raise ValueError("invalid bitmap/checksum")
                if name in checksums and (checksums[name], widths[name]) != (inherited, len(value)):
                    raise ValueError("incompatible point universe")
                checksums[name], widths[name] = inherited, len(value)
                merged[name] = merged.get(name, 0) | int(value, 2)
            if test_index and found != set(merged):
                raise ValueError("missing selected instances")
        shape = xml(paths[0] / f"snps/coverage/db/shape/{metric}.verilog.shape.xml")
        definitions = {}
        for node in shape.iter(tag):
            definitions.setdefault(node.get("chksum"), []).append(node)
        for name, bits in merged.items():
            width = widths[name]
            layouts = [point_layout(metric, d, width) for d in definitions[checksums[name]]]
            if any(layout != layouts[0] for layout in layouts):
                raise ValueError("ambiguous shape definition")
            points, confidence = layouts[0]
            bitmap = format(bits, f"0{width}b")
            report["instances"].setdefault(name, {})[metric] = {
                "checksum": checksums[name], "covered": bitmap.count("1"),
                "total": width, "bits": bitmap, "mapping": confidence,
                "missing": [p for p in points if bitmap[p["offset"]] == "0"]}
        print(metric, "samples", len(paths) - 1, "instances", len(merged), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
