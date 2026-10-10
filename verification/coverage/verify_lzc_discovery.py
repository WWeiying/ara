#!/usr/bin/env python3
"""Verify saved read-only native discovery without rerunning DVE or applying exclusions."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


def verify(directory):
    status = json.loads((directory / "status.json").read_text())
    if status.get("no_exclusions") is not True or status.get("application_approval") is not False:
        raise ValueError("not read-only discovery")
    pins = json.loads((directory / "pins.json").read_text())
    for name, expected in pins.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("discovery input changed: " + name)
    log_path = directory / "DVEfiles/dve_gui.log"
    lines = log_path.read_text().splitlines()
    if "DVE_COVERAGE_EXPORT_DONE" not in lines:
        raise ValueError("missing DVE completion")
    markers = [re.fullmatch(r"LZC_READ_ONLY_DISCOVERY_DONE (\d+)", line) for line in lines]
    counts = [int(m[1]) for m in markers if m]
    if len(counts) != 1 or counts[0] <= 0:
        raise ValueError("ambiguous discovery completion")
    if any(re.search(r"EXPORT_FAILED|checksum.*mismatch|(?:^|\s)(?:Error|Fatal):", line,
                     re.IGNORECASE) for line in lines):
        raise ValueError("DVE error in discovery")
    with (directory / "native-condition-tree.csv").open(newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        expected = ["Depth", "Path", "Meta", *[f"Column{n}" for n in range(12)]]
        if reader.fieldnames != expected or len(rows) != counts[0]:
            raise ValueError("condition tree shape/count differs")
    if any(None in row or not row["Path"] or not row["Meta"] for row in rows):
        raise ValueError("malformed native row")
    if len({row["Path"] for row in rows}) != len(rows):
        raise ValueError("duplicate condition tree paths")
    selected = (directory / "selected_tests.txt").read_text().splitlines()
    if len(selected) != 1:
        raise ValueError("unexpected selected-test population")
    return dict(status="READ_ONLY_DISCOVERY_VERIFIED_NOT_NATIVE_WAIVER_QUALIFICATION",
                original_driver_status=status, native_rows=len(rows), scope=status["scope"],
                no_exclusions=True, application_approval=False,
                input_sha256=pins, artifact_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (log_path, directory / "native-condition-tree.csv",
                              directory / "selected_tests.txt", directory / "summary.csv.partial")},
                correction="Driver inspected stdout instead of the native DVE GUI log; no rerun")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = verify(args.directory.resolve(strict=True))
    with (args.directory / "discovery-verification.json").open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(result["status"], result["native_rows"])


if __name__ == "__main__":
    main()
