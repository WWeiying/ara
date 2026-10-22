#!/usr/bin/env python3
"""Verify a singleton native capture; never authorize aggregate exclusions."""
import argparse
import hashlib
import json
from pathlib import Path

from lzc_native_records import bind_records, parse_records


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory, candidates_path):
    status = json.loads((directory / "status.json").read_text())
    if (status.get("status") != "NATIVE_PILOT_COMPLETE_PENDING_ARTIFACT_VERIFICATION"
            or status.get("capture_only") is not True
            or status.get("application_approval") is not False):
        raise ValueError("not a completed capture-only pilot")
    pins = json.loads((directory / "pins.json").read_text())
    if not pins or any(sha(Path(p)) != h for p, h in pins.items()):
        raise ValueError("capture inputs changed")
    artifacts = ("first.el", "second.el", "initial-empty.el", "reset-empty.el",
                 "final-empty.el", "DVEfiles/dve_gui.log", "status.json", "pins.json")
    hashes = {name: sha(directory / name) for name in artifacts}
    first = parse_records((directory / "first.el").read_text())
    second = parse_records((directory / "second.el").read_text())
    if len(first) != 1 or first != second or first[0]["scope"] != status["scope"]:
        raise ValueError("singleton native roundtrip differs")
    candidates_hash = sha(candidates_path)
    candidates = json.loads(candidates_path.read_text())["candidates"]
    record = first[0]
    selected = [c for c in candidates if all(c["point"][key] == record[key]
                                           for key in ("scope", "expression", "vector"))]
    bind_records(first, selected)
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        if parse_records((directory / name).read_text()):
            raise ValueError("residual exclusions")
    log = (directory / "DVEfiles/dve_gui.log").read_text()
    states = ("before retained=0 target=0", "selected retained=0 target=1",
              "reset retained=0 target=0", "reloaded retained=0 target=1",
              "final retained=0 target=0")
    markers = ["LZC_SINGLE_STATE " + s for s in states]
    if any(log.count(m) != 1 for m in markers):
        raise ValueError("missing or duplicate state audit")
    positions = [log.index(m) for m in markers]
    if positions != sorted(positions) or "LZC_READ_ONLY_DISCOVERY_DONE 1" not in log:
        raise ValueError("incomplete state audit")
    if (any(sha(directory / n) != h for n, h in hashes.items())
            or sha(candidates_path) != candidates_hash
            or any(sha(Path(p)) != h for p, h in pins.items())):
        raise ValueError("evidence changed during verification")
    return dict(status="SINGLE_NATIVE_VECTOR_ARTIFACT_CHECK_PASS",
                capture_directory=str(directory.resolve()), native_records=first,
                artifact_sha256=hashes, input_pins=pins,
                candidates_file=str(candidates_path.resolve()),
                candidates_sha256=candidates_hash, application_approval=False,
                aggregate_exclusions_applied=False,
                limitations="One captured vector; not independent review or full-population qualification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.capture, args.candidates)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"])


if __name__ == "__main__":
    main()
