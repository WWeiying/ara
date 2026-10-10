#!/usr/bin/env python3
"""Validate a Linux boot log and its recorded payload provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_MARKERS = (
    "OpenSBI",
    "Linux version",
    "Ara DSA VCU118 Linux init reached",
    "Linux console, DDR and RVV handoff are alive",
)
USERSPACE_MARKERS = (
    "OpenSBI",
    "Linux version",
    "Ara verification Linux init reached",
    "ARA_LINUX_USERSPACE PASS",
)
FAILURE_MARKERS = (
    "Kernel panic",
    "Oops:",
    "BUG:",
    "segmentation fault",
    "watchdog: BUG",
    "soft lockup",
    "hard LOCKUP",
    "[LINUX_RVV] FAIL",
    "ARA_LINUX_USERSPACE FAIL",
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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


def check_stage_result(
    result_path: Path,
    *,
    expected_stage: Optional[str] = None,
    required_markers: Optional[List[str]] = None,
    require_command: bool = True,
    require_artifacts: bool = True,
) -> Dict[str, object]:
    """Validate stage evidence and its integrity sidecar.

    The sidecar detects accidental or later file changes; it is not a
    cryptographic attestation of who produced the evidence.
    """
    errors: List[str] = []
    checksum_path = result_path.with_name("stage_result.sha256")
    try:
        record = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "errors": [f"invalid stage result: {error}"]}

    if not isinstance(record, dict):
        return {"status": "FAIL", "errors": ["stage result must be a JSON object"]}
    if record.get("schema_version") != 1:
        errors.append("stage result schema_version=1 is required")
    if not checksum_path.is_file():
        errors.append(f"missing stage result checksum: {checksum_path}")
    else:
        checksum_tokens = checksum_path.read_text(encoding="utf-8").split()
        expected = checksum_tokens[0] if checksum_tokens else ""
        actual = sha256(result_path)
        if not SHA256_RE.fullmatch(expected):
            errors.append("stage result checksum is not a SHA-256")
        elif expected.lower() != actual:
            errors.append("stage result SHA-256 mismatch")

    if expected_stage is not None and record.get("stage") != expected_stage:
        errors.append(f"expected stage {expected_stage}, found {record.get('stage')!r}")
    if not record.get("stage"):
        errors.append("stage result stage is missing")
    if require_command:
        command = record.get("command")
        if not isinstance(command, list) or not command or any(
            not isinstance(item, str) or not item for item in command
        ):
            errors.append("stage result command must be a non-empty string list")
        if not isinstance(record.get("command_text"), str) or not record.get("command_text"):
            errors.append("stage result command_text is missing")
        if not isinstance(record.get("cwd"), str) or not record.get("cwd"):
            errors.append("stage result cwd is missing")
        for field in ("created_at", "completed_at"):
            if not isinstance(record.get(field), str) or not record.get(field):
                errors.append(f"stage result {field} is missing")
    if record.get("status") != "PASS":
        errors.append(f"stage status is {record.get('status')!r}, not PASS")
    if record.get("returncode") != 0:
        errors.append(f"stage returncode is {record.get('returncode')!r}")

    console_raw = record.get("console_log")
    console = Path(console_raw) if isinstance(console_raw, str) else None
    if console is None or not console.is_file():
        errors.append("stage console log is missing")
        console_text = ""
    else:
        console_text = console.read_text(encoding="utf-8", errors="replace")
        expected_console_hash = record.get("console_sha256")
        if not isinstance(expected_console_hash, str) or not SHA256_RE.fullmatch(expected_console_hash):
            errors.append("stage console SHA-256 is missing or invalid")
        elif sha256(console) != expected_console_hash.lower():
            errors.append("stage console SHA-256 mismatch")
    declared_markers = record.get("markers")
    if not isinstance(declared_markers, list) or any(
        not isinstance(marker, str) or not marker for marker in declared_markers
    ):
        errors.append("stage result markers must be a non-empty string list")
        declared_markers = []
    if not declared_markers:
        errors.append("stage result must declare at least one marker")
    markers = required_markers or list(declared_markers)
    undeclared = [marker for marker in markers if marker not in declared_markers]
    errors.extend(f"required marker is not recorded in stage result: {marker}" for marker in undeclared)
    marker_status = {marker: marker in console_text for marker in markers}
    errors.extend(f"missing console marker: {marker}" for marker, present in marker_status.items() if not present)
    errors.extend(
        f"failure marker present in stage console: {marker}"
        for marker in FAILURE_MARKERS if marker in console_text
    )

    artifact_hashes = record.get("artifacts", {})
    artifact_paths = record.get("artifact_paths", {})
    if not isinstance(artifact_hashes, dict) or not isinstance(artifact_paths, dict):
        errors.append("stage artifacts and artifact_paths must be objects")
        artifact_status = {}
    else:
        artifact_status = {}
        if require_artifacts and not artifact_hashes:
            errors.append("stage result must contain non-empty artifact hashes")
        if require_artifacts and not artifact_paths:
            errors.append("stage result must contain non-empty artifact paths")
        if set(artifact_hashes) != set(artifact_paths):
            errors.append("stage artifact hashes and paths must have identical keys")
        for name, expected_hash in artifact_hashes.items():
            if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
                errors.append(f"stage artifact SHA-256 is invalid: {name}")
                artifact_status[str(name)] = False
                continue
            raw_path = artifact_paths.get(name)
            path = Path(raw_path) if isinstance(raw_path, str) else None
            if path is None or not path.is_file():
                errors.append(f"stage artifact is missing: {name}")
                artifact_status[str(name)] = False
                continue
            actual_hash = sha256(path)
            artifact_status[str(name)] = actual_hash == str(expected_hash).lower()
            if not artifact_status[str(name)]:
                errors.append(f"stage artifact SHA-256 mismatch: {name}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "stage_result": str(result_path.resolve()),
        "stage": record.get("stage"),
        "markers": marker_status,
        "artifacts": artifact_status,
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
