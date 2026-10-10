#!/usr/bin/env python3
"""Snapshot only this agent's ready binaries/sources/evidence for handoff."""
import argparse
import json
from pathlib import Path
import shutil

from build_gap35_scalar import ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    source = args.selection.resolve(strict=True)
    selection = json.loads(source.read_text())
    dest = source.parent / "frozen"
    dest.mkdir(exist_ok=False)
    hashes, copies = {}, {}

    def snapshot(value):
        path = Path(value).resolve(strict=True)
        if str(path) in copies:
            return copies[str(path)]
        target = dest / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha(path)
        shutil.copyfile(path, target)
        if sha(path) != before or sha(target) != before:
            raise ValueError(f"snapshot drift: {path}")
        hashes[str(target)] = before
        copies[str(path)] = str(target)
        return str(target)

    for case in selection["cases"]:
        case["binary"] = snapshot(case["binary"])
        case["sources"] = [snapshot(p) for p in [*case["sources"], str(Path(__file__).resolve())]]
        case["evidence"] = [snapshot(p) for p in case["evidence"]]
        case["source_audit"] = "Independent known-value scalar C oracle and same-source Spike; " + case["evidence"][0]
    output = source.parent / "selection-frozen.json"
    with output.open("x") as stream:
        json.dump(selection, stream, indent=2)
        stream.write("\n")
    hashes[str(output)] = sha(output)
    for path in (selection["baseline_bits"], str(source)):
        hashes[path] = sha(Path(path))
    (dest / "manifest.json").write_text(json.dumps(dict(sha256=hashes, original_to_snapshot=copies), indent=2) + "\n")
    print(f"Frozen {len(copies)} files for {len(selection['cases'])} cases; SHA-256 verified.")
    print(output)


if __name__ == "__main__":
    main()
