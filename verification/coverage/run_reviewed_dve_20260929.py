#!/usr/bin/env python3
"""Snapshot the exporter to apply new waivers without changing frozen runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--inputs-file", required=True, type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    output = args.output.resolve()
    bundle = Path(str(output) + ".tools")
    if output.exists() or bundle.exists():
        parser.error("Output and snapshot directories must be new")
    bundle.mkdir(parents=True)
    (bundle / "dve_hierarchy").mkdir()
    (bundle / "waivers").mkdir()
    sources = {
        "waiver_base.py": here / "prepare_dve_waivers.py",
        "prepare_dve_waivers.py": here / "reviewed_20260929/prepare_dve_waivers.py",
        "dve_waivers.tcl": here / "dve_waivers.tcl",
        "dve_hierarchy/run_dve_coverage.sh": here / "dve_hierarchy/run_dve_coverage.sh",
        "dve_hierarchy/export_dve_coverage.tcl": here / "dve_hierarchy/export_dve_coverage.tcl",
    }
    for target, source in sources.items():
        shutil.copyfile(source, bundle / target)
    points = (here / "waivers/operand_flush.el").read_bytes()
    points += b"\n" + (here / "reviewed_20260929/constant_inputs.el").read_bytes()
    (bundle / "waivers/operand_flush.el").write_bytes(points)
    hashes = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(bundle.rglob("*")) if p.is_file()}
    (bundle / "snapshot.json").write_text(json.dumps(hashes, indent=2) + "\n")
    env = dict(os.environ, DVE_WAIVERS="auto")
    return subprocess.call(["bash", str(bundle / "dve_hierarchy/run_dve_coverage.sh"),
                            str(output), "--inputs-file", str(args.inputs_file.resolve())], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
