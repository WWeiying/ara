#!/usr/bin/env python3
"""Check a VCU118 run manifest before accepting FPGA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SIGNOFF_CONSOLE_MARKERS = (
    "OpenSBI",
    "Linux version",
    "Ara DSA VCU118 Linux init reached",
    "Linux console, DDR and RVV handoff are alive",
)
FAILURE_MARKERS = (
    "Kernel panic",
    "Oops:",
    "BUG:",
    "segmentation fault",
    "UVM_FATAL",
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _artifact_record(
    name: str,
    value: object,
    errors: List[str],
    *,
    require_hash: bool = False,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, str]]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        errors.append(f"artifact {name} must contain a path")
        return None
    path = Path(value["path"])
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    if not path.is_file():
        errors.append(f"artifact {name} is missing: {path}")
        return None
    actual = sha256(path)
    expected = value.get("sha256")
    if require_hash and not isinstance(expected, str):
        errors.append(f"artifact {name} must contain a SHA-256 for signoff")
    elif require_hash and not SHA256_RE.fullmatch(expected):
        errors.append(f"artifact {name} SHA-256 must be 64 hexadecimal characters")
    elif expected is not None and str(expected).lower() != actual:
        errors.append(f"artifact {name} SHA-256 mismatch")
    return {"path": str(path.resolve()), "sha256": actual}


REQUIRED_SIGNOFF_TESTS = (
    "reset_uart_ddr",
    "baremetal_rvv_signature",
    "linux_boot",
    "rvv_fallback_userspace",
    "qbs_akv_userspace",
    "context_switch_and_fault_return",
    "long_model_smoke",
)


def _check_test_evidence(
    test: Mapping[str, object], errors: List[str], *, base_dir: Path
) -> None:
    name = str(test.get("name", "<unnamed>"))
    command = test.get("command")
    if not command or (not isinstance(command, (str, list))):
        errors.append(f"FPGA test {name} must record a command")
    evidence = test.get("evidence")
    if not isinstance(evidence, dict):
        errors.append(f"FPGA test {name} must contain an evidence object")
        return
    for field in ("log", "result"):
        raw_path = evidence.get(field)
        path = Path(raw_path) if isinstance(raw_path, str) else None
        if path is not None and not path.is_absolute():
            path = base_dir / path
        if path is None or not path.is_file():
            errors.append(f"FPGA test {name} evidence {field} is missing")
    input_hashes = evidence.get("input_hashes")
    if not isinstance(input_hashes, dict) or not input_hashes:
        errors.append(f"FPGA test {name} must record non-empty input_hashes")
    else:
        for input_name, digest in input_hashes.items():
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                errors.append(f"FPGA test {name} input hash is invalid: {input_name}")


def check_manifest(
    manifest_path: Path,
    *,
    require_signoff: bool = False,
    required_tests: Optional[List[str]] = None,
) -> Dict[str, object]:
    errors: List[str] = []
    base_dir = manifest_path.resolve().parent
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
            record = _artifact_record(
                str(name), value, errors, require_hash=require_signoff, base_dir=base_dir
            )
            if record is not None:
                artifacts[str(name)] = record
        for required in ("bitstream", "software"):
            if required not in artifacts:
                errors.append(f"required artifact is missing: {required}")

    if manifest.get("ddr_calibration") is not True:
        errors.append("ddr_calibration must be true")
    if manifest.get("reset_uart_smoke") is not True:
        errors.append("reset_uart_smoke must be true")
    if require_signoff:
        if manifest.get("flow_status") != "COMPLETE":
            errors.append("flow_status=COMPLETE is required for FPGA signoff")
        if manifest.get("bitstream_generated") is not True:
            errors.append("bitstream_generated=true is required for FPGA signoff")

    console = manifest.get("console_log")
    markers = manifest.get("console_markers", [])
    console_path = Path(console) if isinstance(console, str) else None
    if console_path is not None and not console_path.is_absolute():
        console_path = base_dir / console_path
    if console_path is None or not console_path.is_file():
        errors.append("console_log is missing")
    elif not isinstance(markers, list) or any(not isinstance(marker, str) for marker in markers):
        errors.append("console_markers must be a list of strings")
    else:
        text = console_path.read_text(encoding="utf-8", errors="replace")
        if require_signoff:
            missing_required = [marker for marker in SIGNOFF_CONSOLE_MARKERS if marker not in markers]
            errors.extend(
                f"signoff console_markers must declare fixed marker: {marker}"
                for marker in missing_required
            )
            errors.extend(
                f"failure marker present in FPGA console: {marker}"
                for marker in FAILURE_MARKERS if marker in text
            )
        errors.extend(f"missing console marker: {marker}" for marker in markers if marker not in text)

    if require_signoff and (not isinstance(markers, list) or not markers):
        errors.append("console_markers must be non-empty for FPGA signoff")

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
    if require_signoff:
        for test in tests:
            if isinstance(test, dict) and str(test.get("status", "")).upper() == "PASS":
                _check_test_evidence(test, errors, base_dir=base_dir)
        passed_names = {
            str(test.get("name")) for test in tests
            if isinstance(test, dict) and str(test.get("status", "")).upper() == "PASS"
        }
        required = required_tests or list(REQUIRED_SIGNOFF_TESTS)
        missing = sorted(set(required) - passed_names)
        if missing:
            errors.append(f"required FPGA signoff tests are missing: {missing}")

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
    payload = check_manifest(args.manifest, require_signoff=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
