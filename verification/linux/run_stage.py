#!/usr/bin/env python3
"""Run one Linux/QEMU/RTL/board stage and emit reproducible evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_artifacts(values: List[str]) -> Dict[str, Path]:
    artifacts: Dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"artifact must use NAME=PATH: {value}")
        name, raw_path = value.split("=", 1)
        if not name or not raw_path:
            raise ValueError(f"artifact must use NAME=PATH: {value}")
        artifacts[name] = Path(raw_path)
    return artifacts


def run_stage(
    stage: str,
    output: Path,
    command: List[str],
    markers: List[str],
    artifacts: Dict[str, Path],
    timeout_s: int,
) -> Dict[str, object]:
    if not command:
        raise ValueError("a command after -- is required")
    if timeout_s <= 0:
        raise ValueError("timeout must be positive")

    output.mkdir(parents=True, exist_ok=True)
    console = output / "console.log"
    metadata: Dict[str, object] = {
        "schema_version": 1,
        "stage": stage,
        "status": "RUNNING",
        "created_at": now(),
        "command": command,
        "command_text": shlex.join(command),
        "cwd": os.getcwd(),
        "timeout_s": timeout_s,
        "artifacts": {},
        "artifact_paths": {name: str(path.resolve()) for name, path in artifacts.items()},
        "markers": markers,
    }
    (output / "command.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    with console.open("wb") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            returncode = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    elapsed_s = time.monotonic() - started
    text = console.read_text(encoding="utf-8", errors="replace")
    missing_markers = [marker for marker in markers if marker not in text]

    artifact_hashes: Dict[str, str] = {}
    errors: List[str] = []
    for name, path in artifacts.items():
        if not path.is_file():
            errors.append(f"missing artifact: {name}: {path}")
        else:
            artifact_hashes[name] = sha256(path)
    errors.extend(f"missing marker: {marker}" for marker in missing_markers)
    if timed_out:
        status = "TIMEOUT"
        errors.insert(0, f"command exceeded timeout {timeout_s}s")
    elif returncode != 0:
        status = "FAIL"
        errors.insert(0, f"command exited with {returncode}")
    elif errors:
        status = "FAIL"
    else:
        status = "PASS"

    result = {
        **metadata,
        "status": status,
        "completed_at": now(),
        "elapsed_s": elapsed_s,
        "returncode": returncode,
        "console_log": str(console.resolve()),
        "console_sha256": sha256(console),
        "artifacts": artifact_hashes,
        "artifact_paths": {name: str(path.resolve()) for name, path in artifacts.items()},
        "missing_markers": missing_markers,
        "errors": errors,
    }
    result_path = output / "stage_result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "stage_result.sha256").write_text(
        sha256(result_path) + "  stage_result.json\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("qemu", "rtl", "board"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    try:
        result = run_stage(
            args.stage,
            args.output.resolve(),
            command,
            list(args.marker),
            parse_artifacts(args.artifact),
            args.timeout,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve())}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
