#!/usr/bin/env python3
"""Close a QBS host/RTL unit-validation run into auditable artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


PROFILE_CASE_RE = re.compile(
    r"QBS RTL case (\d+) PASS profile=(\d+) M=(\d+) rows=(\d+) pattern=(\d+)"
)
COMMAND_CASE_RE = re.compile(
    r"QBS command case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) Kb=(\d+) "
    r"layouts=(\d+)/(\d+)"
)
ENGINE_CASE_RE = re.compile(
    r"QBS end-to-end case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) Kb=(\d+) "
    r"layouts=(\d+)/(\d+) cycles=(\d+)"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256_manifest(path: Path) -> int:
    require(path.is_file(), f"missing SHA-256 manifest: {path}")
    count = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        digest, filename = line.split(maxsplit=1)
        artifact = Path(filename.lstrip("* "))
        require(artifact.is_file(), f"manifest artifact is missing: {artifact}")
        require(sha256(artifact) == digest,
                f"manifest hash no longer matches: {artifact}")
        count += 1
    require(count > 0, f"empty SHA-256 manifest: {path}")
    return count


def read_log(root: Path, name: str) -> tuple[Path, str]:
    path = root / "logs" / name
    require(path.is_file() and path.stat().st_size > 0, f"missing log: {path}")
    text = path.read_text(errors="replace")
    require("Error-" not in text, f"VCS error marker in {path}")
    require("UVM_ERROR" not in text and "UVM_FATAL" not in text,
            f"UVM failure marker in {path}")
    return path, text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--expected-git-head")
    args = parser.parse_args()

    root = args.run_root.resolve()
    require((root / "DONE").is_file(), f"unit validation is incomplete: {root}")
    require((root / "status").read_text().strip() == "PASS",
            "unit-validation runner did not pass")
    require((root / "driver_exit_code").read_text().strip() == "0",
            "unit-validation runner returned nonzero")

    git_head = (root / "git_head").read_text().strip()
    if args.expected_git_head:
        require(git_head == args.expected_git_head,
                f"source revision mismatch: {git_head}")
    require((root / "git_diff.patch").read_bytes() == b"",
            "validation worktree contains tracked source changes")

    source_entries = verify_sha256_manifest(root / "source_files.sha256")
    dependency_entries = verify_sha256_manifest(root / "dependency_files.sha256")
    artifact_entries = verify_sha256_manifest(root / "artifacts.sha256")

    host_path, host = read_log(root, "host.log")
    for marker in (
        "QBS ABI generated files are up to date",
        "RVV x32 and QBS R4 repacking regressions: PASS",
        "qbs_ref_test: PASS",
    ):
        require(marker in host, f"missing host-validation marker: {marker}")

    profile_path, profile = read_log(root, "rtl_profile.log")
    profile_cases = [tuple(map(int, match.groups()))
                     for match in PROFILE_CASE_RE.finditer(profile)]
    require(len(profile_cases) == 432,
            f"profile RTL has {len(profile_cases)} cases, expected 432")
    require([case[0] for case in profile_cases] == list(range(432)),
            "profile RTL case ordinals are incomplete or reordered")
    observed_profile_space = {case[1:] for case in profile_cases}
    expected_profile_space = {
        (profile_id, m, rows, pattern)
        for profile_id in range(1, 10)
        for m in range(1, 5)
        for rows in range(1, 5)
        for pattern in range(3)
    }
    require(observed_profile_space == expected_profile_space,
            "profile RTL does not cover the full 9x4x4x3 Cartesian product")
    require("QBS profile engine PASS: 432 cases" in profile,
            "profile RTL final marker is missing")

    command_path, command = read_log(root, "rtl_command.log")
    command_cases = [tuple(map(int, match.groups()))
                     for match in COMMAND_CASE_RE.finditer(command)]
    require(len(command_cases) == 22,
            f"command RTL has {len(command_cases)} cases, expected 22")
    require([case[0] for case in command_cases] == list(range(22)),
            "command RTL case ordinals are incomplete or reordered")
    require("QBS command fault discard PASS" in command,
            "command fault-discard check is missing")
    require("QBS command engine PASS: 22 functional cases" in command,
            "command RTL final marker is missing")

    engine_path, engine = read_log(root, "rtl_engine.log")
    engine_cases = [tuple(map(int, match.groups()))
                    for match in ENGINE_CASE_RE.finditer(engine)]
    require(len(engine_cases) == 22,
            f"end-to-end RTL has {len(engine_cases)} cases, expected 22")
    require([case[0] for case in engine_cases] == list(range(22)),
            "end-to-end RTL case ordinals are incomplete or reordered")
    for marker in (
        "QBS validation atomic-fault PASS",
        "QBS MMU atomic-fault PASS",
        "QBS AXI atomic-fault PASS",
        "QBS PMA atomic-fault PASS",
        "QBS engine PASS: 22 functional cases plus four fault classes",
    ):
        require(marker in engine, f"missing end-to-end marker: {marker}")

    leaf_logs = {
        "descriptor": "QBS descriptor decoder PASS",
        "read": "QBS read engine PASS",
        "commit": "QBS commit PASS",
    }
    leaf_paths: dict[str, Path] = {}
    for name, marker in leaf_logs.items():
        path, text = read_log(root, f"rtl_{name}.log")
        require(marker in text, f"missing {name} RTL marker: {marker}")
        leaf_paths[name] = path

    row = {
        "git_head": git_head,
        "host_checks": 3,
        "profile_cases_passed": len(profile_cases),
        "profile_cases_expected": 432,
        "weight_profiles": 9,
        "m_values": 4,
        "row_values": 4,
        "data_patterns": 3,
        "command_cases_passed": len(command_cases),
        "command_cases_expected": 22,
        "end_to_end_cases_passed": len(engine_cases),
        "end_to_end_cases_expected": 22,
        "command_fault_classes_passed": 4,
        "descriptor_test": "PASS",
        "read_engine_test": "PASS",
        "commit_test": "PASS",
        "source_manifest_entries": source_entries,
        "dependency_manifest_entries": dependency_entries,
        "artifact_manifest_entries": artifact_entries,
        "host_log_sha256": sha256(host_path),
        "profile_log_sha256": sha256(profile_path),
        "command_log_sha256": sha256(command_path),
        "engine_log_sha256": sha256(engine_path),
        "descriptor_log_sha256": sha256(leaf_paths["descriptor"]),
        "read_log_sha256": sha256(leaf_paths["read"]),
        "commit_log_sha256": sha256(leaf_paths["commit"]),
        "source_manifest_sha256": sha256(root / "source_files.sha256"),
        "dependency_manifest_sha256": sha256(root / "dependency_files.sha256"),
        "artifact_manifest_sha256": sha256(root / "artifacts.sha256"),
    }

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    summary = {
        "run_root": str(root),
        "status": "PASS",
        "coverage_identity": "9 profiles x 4 M x 4 rows x 3 patterns",
        **row,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {args.output_csv} and {args.output_json}")


if __name__ == "__main__":
    main()
