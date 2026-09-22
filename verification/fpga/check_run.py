#!/usr/bin/env python3
"""Check a VCU118 run manifest before accepting FPGA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(name: str, value: object, errors: List[str]) -> Optional[Dict[str, str]]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        errors.append(f"artifact {name} must contain a path")
        return None
    path = Path(value["path"])
    if not path.is_file():
        errors.append(f"artifact {name} is missing: {path}")
        return None
    actual = sha256(path)
    expected = value.get("sha256")
    if expected is not None and str(expected).lower() != actual:
        errors.append(f"artifact {name} SHA-256 mismatch")
    return {"path": str(path.resolve()), "sha256": actual}


def check_manifest(manifest_path: Path) -> Dict[str, object]:
    errors: List[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "errors": [f"invalid manifest: {error}"]}
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return {"status": "FAIL", "errors": ["schema_version=1 is required"]}

    for field in ("board", "bitstream_tool", "vivado_version", "rtl_commit"):
        if not manifest.get(field):
            errors.append(f"missing manifest field: {field}")
    if manifest.get("board") != "VCU118":
        errors.append(f"expected board VCU118, found {manifest.get('board')!r}")
    clock_mhz = manifest.get("clock_mhz")
    if not isinstance(clock_mhz, (int, float)) or clock_mhz <= 0:
        errors.append("clock_mhz must be positive")

    artifacts: Dict[str, Dict[str, str]] = {}
    raw_artifacts = manifest.get("artifacts", {})
    if not isinstance(raw_artifacts, dict):
        errors.append("artifacts must be an object")
    else:
        for name, value in raw_artifacts.items():
            record = _artifact_record(str(name), value, errors)
            if record is not None:
                artifacts[str(name)] = record
        for required in ("bitstream", "software"):
            if required not in artifacts:
                errors.append(f"required artifact is missing: {required}")

    if manifest.get("ddr_calibration") is not True:
        errors.append("ddr_calibration must be true")
    if manifest.get("reset_uart_smoke") is not True:
        errors.append("reset_uart_smoke must be true")

    console = manifest.get("console_log")
    markers = manifest.get("console_markers", [])
    if not isinstance(console, str) or not Path(console).is_file():
        errors.append("console_log is missing")
    elif not isinstance(markers, list) or any(not isinstance(marker, str) for marker in markers):
        errors.append("console_markers must be a list of strings")
    else:
        text = Path(console).read_text(encoding="utf-8", errors="replace")
        errors.extend(f"missing console marker: {marker}" for marker in markers if marker not in text)

    tests = manifest.get("tests", [])
    if not isinstance(tests, list) or not tests:
        errors.append("tests must be a non-empty list")
        tests = []
    failed_tests = [
        str(test.get("name", "<unnamed>"))
        for test in tests
        if not isinstance(test, dict) or str(test.get("status", "")).upper() != "PASS"
    ]
    if failed_tests:
        errors.append(f"failed or malformed FPGA tests: {failed_tests}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "manifest": str(manifest_path.resolve()),
        "board": manifest.get("board"),
        "clock_mhz": clock_mhz,
        "rtl_commit": manifest.get("rtl_commit"),
        "artifacts": artifacts,
        "test_count": len(tests),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = check_manifest(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
