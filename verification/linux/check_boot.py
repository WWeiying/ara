#!/usr/bin/env python3
"""Validate a Linux boot log and its immutable payload provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List


DEFAULT_MARKERS = (
    "OpenSBI",
    "Linux version",
    "Ara DSA VCU118 Linux init reached",
    "Linux console, DDR and RVV handoff are alive",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_boot(log: Path, markers: List[str], artifacts: Dict[str, Path]) -> Dict[str, object]:
    errors: List[str] = []
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return {"status": "FAIL", "errors": [f"cannot read console log: {error}"]}
    missing = [marker for marker in markers if marker not in text]
    errors.extend(f"missing console marker: {marker}" for marker in missing)
    artifact_hashes: Dict[str, str] = {}
    for name, path in artifacts.items():
        if not path.is_file():
            errors.append(f"missing artifact: {name}: {path}")
        else:
            artifact_hashes[name] = sha256(path)
    return {
        "status": "PASS" if not errors else "FAIL",
        "console_log": str(log.resolve()),
        "markers": {marker: marker not in missing for marker in markers},
        "artifacts": artifact_hashes,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--marker", action="append", dest="markers")
    parser.add_argument(
        "--artifact", action="append", default=[], metavar="NAME=PATH",
        help="payload whose SHA-256 must be recorded; repeatable",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    markers = args.markers or list(DEFAULT_MARKERS)
    artifacts: Dict[str, Path] = {}
    for item in args.artifact:
        if "=" not in item:
            parser.error(f"--artifact requires NAME=PATH: {item}")
        name, raw_path = item.split("=", 1)
        if not name or not raw_path:
            parser.error(f"--artifact requires NAME=PATH: {item}")
        artifacts[name] = Path(raw_path)
    payload = check_boot(args.log, markers, artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
