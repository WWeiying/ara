#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import yaml

from ara_verify.stimulus_coverage import merge_stimulus_coverage


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY = REPO_ROOT / "verification" / "verify.py"
TESTLIST = REPO_ROOT / "verification" / "riscv_dv" / "testlist.yaml"
CHECKPOINT_PROFILES = {
    "ara_dsa_rvv1_signature_smoke",
    "ara_dsa_rvv1_checkpoint_regression",
}
MINIMUM_CAMPAIGN_INVENTORY = {"rvv": 207, "app": 50, "random": 142}
REQUIRED_DIRECTED_TESTS = {
    "rvv:vaadd",
    "rvv:vaaddu",
    "rvv:vasub",
    "rvv:vasubu",
    "rvv:vaverage_matrix",
    "rvv:vdiv_vstart_edges",
    "rvv:vfp_vstart_edges",
    "rvv:vmask_carry_tail_edges",
    "rvv:vmask_compare_edges",
    "rvv:vmask_logical_matrix",
    "rvv:vmask_mem_emul_edges",
    "rvv:vmask_scalar_handoff",
    "rvv:vcpop",
    "rvv:vfirst",
    "rvv:vid_queue_edges",
    "rvv:vrepair_edges",
    "rvv:vwiden_lmul4_edges",
    "rvv:vwiden_overlap_edges",
    "rvv:vreduction_lmul_edges",
    "rvv:vreduction_overlap_edges",
    "rvv:vnclip_edges",
    "rvv:vslide_mask_edges",
    "rvv:vrgather_edges",
    "rvv:vcompress_edges",
    "rvv:vsegment_emul_edges",
    "rvv:villegal_segment_recovery",
    "rvv:villegal_vstart_ops",
    "rvv:vindexed_vstart_edges",
    "rvv:vunit_vstart_edges",
    "rvv:vwhole_vstart_edges",
    "rvv:vwar_pending_source_edges",
    "rvv:vstore_signature",
    "rvv:vstore_mask_tail_edges",
}
REQUIRED_RANDOM_PROFILES = {
    "ara_dsa_rvv1_signature_smoke": 1,
    "ara_dsa_rvv1_checkpoint_regression": 10,
    "ara_dsa_rvv1_smoke": 1,
    "ara_dsa_rvv1_arithmetic": 10,
    "ara_dsa_rvv1_load_store": 10,
    "ara_dsa_rvv1_integer_stress": 10,
    "ara_dsa_rvv1_fp32": 10,
    "ara_dsa_rvv1_fp64": 10,
    "ara_dsa_rvv1_vtype_churn": 10,
    "ara_dsa_rvv1_load_store_slide": 10,
    "ara_dsa_rvv1_mixed_control": 10,
    "ara_dsa_rvv1_nightly": 50,
}
REQUIRED_RANDOM_COVERAGE = {
    "families": {
        "configuration", "fixed_point", "floating_point", "integer_arithmetic",
        "load_store", "mask_logical", "mask_other", "narrowing", "permutation",
        "reduction", "widening",
    },
    "memory_modes": {
        "unit_stride", "strided", "indexed", "segment", "mask",
        "whole_register", "fault_first",
    },
    "sew": {"e8", "e16", "e32", "e64"},
    "lmul": {"mf8", "mf4", "mf2", "m1", "m2", "m4", "m8"},
    "tail_policy": {"ta", "tu"},
    "mask_policy": {"ma", "mu"},
}
SOURCE_SUFFIXES = {
    ".c", ".h", ".json", ".patch", ".py", ".sv", ".svh", ".yaml", ".yml"
}
SOURCE_EXCLUDE_DIRS = {
    ".git", "__pycache__", "build", "deps", "install", "out", "sim", "third-party", "tools"
}
SOURCE_EXCLUDE_FILES = {"apps/compiler_macros.h"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the complete directed, application, and random RVV campaign"
    )
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument(
        "--generator-simv", type=Path,
        help="reuse one precompiled VCS riscv-dv generator for every random profile",
    )
    parser.add_argument(
        "--spike", type=Path, required=True,
        help="explicit Ara-compatible Spike executable used by every random profile",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--random-jobs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--spike-timeout", type=int, default=300)
    parser.add_argument("--watchdog-cycles", type=int, default=1000000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot() -> Dict[str, object]:
    digest = hashlib.sha256()
    files: List[str] = []
    for root in (REPO_ROOT / "hardware", REPO_ROOT / "apps", REPO_ROOT / "verification"):
        for path in sorted(root.rglob("*")):
            relative_parts = path.relative_to(root).parts
            if not path.is_file() or any(part in SOURCE_EXCLUDE_DIRS for part in relative_parts):
                continue
            if path.suffix not in SOURCE_SUFFIXES and path.name not in {"Makefile", "Makefrag"}:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative in SOURCE_EXCLUDE_FILES:
                continue
            files.append(relative)
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "file_count": len(files)}


def record_completed_source_snapshot(
    metadata: Dict[str, object], components: Dict[str, int], completed: Dict[str, object]
) -> None:
    metadata["completed_source_snapshot"] = completed
    if completed == metadata["source_snapshot"]:
        components["source_snapshot"] = 0
        metadata.pop("source_snapshot_drift", None)
        return
    components["source_snapshot"] = 1
    metadata["source_snapshot_drift"] = {
        "started": metadata["source_snapshot"],
        "completed": completed,
    }


def random_profiles() -> List[Tuple[str, int]]:
    raw = yaml.safe_load(TESTLIST.read_text(encoding="utf-8"))
    profiles: List[Tuple[str, int]] = []
    for item in raw:
        name = str(item["test"])
        iterations = int(item["iterations"])
        if iterations <= 0:
            raise ValueError(f"profile {name} has invalid iterations={iterations}")
        profiles.append((name, iterations))
    return profiles


def catalog_counts() -> Dict[str, int]:
    result = subprocess.run(
        [sys.executable, str(VERIFY), "list", "--suite", "full"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    counts = {"app": 0, "rvv": 0}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in counts:
            counts[fields[1]] += 1
    counts["full"] = counts["app"] + counts["rvv"]
    return counts


def catalog_test_names() -> set[str]:
    result = subprocess.run(
        [sys.executable, str(VERIFY), "list", "--suite", "full"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    return {
        fields[0]
        for line in result.stdout.splitlines()
        if (fields := line.split())
    }


def run_logged(name: str, command: Sequence[object], log_path: Path) -> Tuple[str, int]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[START] {name}", flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(str(part) for part in command) + "\n")
        log.flush()
        result = subprocess.run(
            [str(part) for part in command],
            cwd=REPO_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    print(f"[DONE ] {name} rc={result.returncode}", flush=True)
    return name, result.returncode


def random_command(
    profile: str, output: Path, simv: Path, args: argparse.Namespace
) -> List[object]:
    command: List[object] = [
        sys.executable,
        VERIFY,
        "run-rvv",
        "--test",
        profile,
        "--seed",
        args.seed,
        "--simv",
        simv,
        "--output",
        output,
        "--timeout",
        args.timeout,
        "--spike-timeout",
        args.spike_timeout,
        "--watchdog-cycles",
        args.watchdog_cycles,
    ]
    if getattr(args, "generator_simv", None) is not None:
        command.extend(["--generator-simv", args.generator_simv])
    if getattr(args, "spike", None) is not None:
        command.extend(["--spike", args.spike])
    if profile in CHECKPOINT_PROFILES:
        command.append("--vector-checkpoints")
    else:
        command.append("--vector-signature")
    command.append("--vector-commit-compare")
    return command


def directed_command(output: Path, simv: Path, args: argparse.Namespace) -> List[object]:
    return [
        sys.executable,
        VERIFY,
        "run",
        "full",
        "--jobs",
        args.jobs,
        "--seed",
        args.seed,
        "--simv",
        simv,
        "--output",
        output,
        "--timeout",
        args.timeout,
    ]


def validate_inventory(expected: Dict[str, int]) -> None:
    missing = {
        kind: {"observed": expected.get(kind, 0), "minimum": minimum}
        for kind, minimum in MINIMUM_CAMPAIGN_INVENTORY.items()
        if expected.get(kind, 0) < minimum
    }
    if missing:
        raise RuntimeError(f"campaign inventory below required coverage: {missing}")


def validate_required_directed_tests(test_names: set[str]) -> None:
    missing = sorted(REQUIRED_DIRECTED_TESTS - test_names)
    if missing:
        raise RuntimeError(f"campaign is missing required directed tests: {missing}")


def validate_required_random_profiles(profiles: List[Tuple[str, int]]) -> None:
    observed: Dict[str, int] = {}
    duplicates: List[str] = []
    for name, iterations in profiles:
        if name in observed:
            duplicates.append(name)
        observed[name] = iterations
    if duplicates:
        raise RuntimeError(f"campaign has duplicate random profiles: {sorted(set(duplicates))}")
    deficient = {
        name: {"observed": observed.get(name, 0), "minimum": minimum}
        for name, minimum in REQUIRED_RANDOM_PROFILES.items()
        if observed.get(name, 0) < minimum
    }
    if deficient:
        raise RuntimeError(f"campaign random profile coverage is incomplete: {deficient}")


def validate_random_stimulus_coverage(
    coverage: Dict[str, object], profiles: List[Tuple[str, int]]
) -> None:
    expected_profiles = dict(profiles)
    observed_profiles: Dict[str, int] = {}
    duplicates: List[str] = []
    profile_records = coverage.get("profiles", [])
    if not isinstance(profile_records, list):
        raise RuntimeError("random stimulus coverage has no profile list")
    for item in profile_records:
        if not isinstance(item, dict):
            raise RuntimeError("random stimulus coverage has an invalid profile entry")
        name = str(item.get("test", ""))
        if name in observed_profiles:
            duplicates.append(name)
        observed_profiles[name] = int(item.get("source_count", 0))
    if duplicates:
        raise RuntimeError(
            f"random stimulus coverage has duplicate profiles: {sorted(set(duplicates))}"
        )
    profile_mismatch = {
        name: {"observed": observed_profiles.get(name, 0), "expected": iterations}
        for name, iterations in expected_profiles.items()
        if observed_profiles.get(name, 0) != iterations
    }
    unexpected_profiles = sorted(set(observed_profiles) - set(expected_profiles))
    if profile_mismatch or unexpected_profiles:
        raise RuntimeError(
            "random stimulus coverage profile/source mismatch: "
            f"profiles={profile_mismatch}, unexpected={unexpected_profiles}"
        )

    aggregate = coverage.get("aggregate")
    if not isinstance(aggregate, dict):
        raise RuntimeError("random stimulus coverage has no aggregate object")
    missing: Dict[str, List[str]] = {}
    for dimension, required in REQUIRED_RANDOM_COVERAGE.items():
        values = aggregate.get(dimension, {})
        if not isinstance(values, dict):
            missing[dimension] = sorted(required)
            continue
        absent = sorted(name for name in required if int(values.get(name, 0)) <= 0)
        if absent:
            missing[dimension] = absent
    if int(coverage.get("vector_instruction_count", 0)) <= 0:
        missing["totals"] = ["vector_instruction_count"]
    if int(coverage.get("masked_instruction_count", 0)) <= 0:
        missing.setdefault("totals", []).append("masked_instruction_count")
    if missing:
        raise RuntimeError(f"random stimulus semantic coverage is incomplete: {missing}")


def collect_results(output: Path, profiles: List[Tuple[str, int]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    full_summary = output / "directed_apps" / "summary.json"
    split_summaries = [
        output / "directed_rvv" / "summary.json",
        output / "applications" / "summary.json",
    ]
    suite_summaries = [full_summary] if full_summary.is_file() else split_summaries
    for summary in suite_summaries:
        if not summary.is_file():
            continue
        for item in json.loads(summary.read_text(encoding="utf-8")):
            rows.append({
                "class": item["kind"],
                "profile": "",
                "name": item["name"],
                "seed": "",
                "status": item["status"],
                "reason": item.get("reason", ""),
                "artifact_dir": item.get("artifact_dir", ""),
            })
    for profile, _ in profiles:
        summary = output / "random" / profile / "summary.json"
        if not summary.is_file():
            continue
        for item in json.loads(summary.read_text(encoding="utf-8")):
            comparison = item.get("comparison", {})
            mismatch = comparison.get("mismatch") or {}
            reason = comparison.get("reason", "") or mismatch.get("reason", "")
            rows.append({
                "class": "random",
                "profile": profile,
                "name": item["name"],
                "seed": item["seed"],
                "status": item["status"],
                "reason": reason,
                "artifact_dir": item.get("artifact_dir", ""),
            })
    return rows


def duplicate_result_identities(
    rows: List[Dict[str, object]],
) -> List[Tuple[str, str, str, str]]:
    identities = [
        (str(row["class"]), str(row["profile"]), str(row["name"]), str(row["seed"]))
        for row in rows
    ]
    return sorted(identity for identity, count in Counter(identities).items() if count > 1)


def results_complete(rows: List[Dict[str, object]], expected: Dict[str, int]) -> bool:
    observed = Counter(str(row["class"]) for row in rows)
    class_counts_match = all(
        observed[kind] == expected[kind] for kind in ("rvv", "app", "random")
    )
    return (
        len(rows) == expected["total"] and class_counts_match and
        not duplicate_result_identities(rows)
    )


def write_summary(
    output: Path,
    rows: List[Dict[str, object]],
    expected: Dict[str, int],
    components: Dict[str, int],
) -> bool:
    status_counts: Dict[str, int] = {}
    class_counts: Dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        category = str(row["class"])
        class_counts[category] = class_counts.get(category, 0) + 1
    duplicates = duplicate_result_identities(rows)
    complete = results_complete(rows, expected)
    component_failures = {
        name: returncode for name, returncode in components.items() if returncode != 0
    }
    all_pass = (
        complete and not component_failures and
        all(row["status"] == "PASS" for row in rows)
    )
    payload = {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "verdict": "PASS" if all_pass else ("FAIL" if complete else "INCOMPLETE"),
        "completed_at": datetime.now().astimezone().isoformat(),
        "expected": expected,
        "observed": {"total": len(rows), "by_class": class_counts},
        "duplicate_results": [list(identity) for identity in duplicates],
        "status_counts": status_counts,
        "component_returncodes": components,
        "component_failures": component_failures,
        "results": rows,
    }
    (output / "campaign_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output / "campaign_summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["class", "profile", "name", "seed", "status", "reason", "artifact_dir"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return all_pass


def main() -> int:
    args = parse_args()
    if args.jobs <= 0 or args.random_jobs <= 0:
        raise ValueError("parallel job counts must be positive")
    simv = args.simv.resolve()
    if not simv.is_file():
        raise FileNotFoundError(simv)
    generator_simv = args.generator_simv.resolve() if args.generator_simv else None
    if generator_simv is not None and not generator_simv.is_file():
        raise FileNotFoundError(generator_simv)
    args.generator_simv = generator_simv
    spike = args.spike.resolve()
    if not spike.is_file():
        raise FileNotFoundError(spike)
    if not os.access(spike, os.X_OK):
        raise PermissionError(f"Spike is not executable: {spike}")
    args.spike = spike
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    profiles = random_profiles()
    validate_required_random_profiles(profiles)
    catalog = catalog_counts()
    expected_random = sum(iterations for _, iterations in profiles)
    expected = {
        "rvv": catalog["rvv"],
        "app": catalog["app"],
        "random": expected_random,
        "total": catalog["full"] + expected_random,
    }
    validate_inventory(expected)
    validate_required_directed_tests(catalog_test_names())

    metadata = {
        "status": "DRY_RUN" if args.dry_run else "RUNNING",
        "created_at": datetime.now().astimezone().isoformat(),
        "expected": expected,
        "profiles": [{"name": name, "iterations": iterations} for name, iterations in profiles],
        "required_directed_tests": sorted(REQUIRED_DIRECTED_TESTS),
        "required_random_profiles": REQUIRED_RANDOM_PROFILES,
        "required_random_coverage": {
            dimension: sorted(required)
            for dimension, required in REQUIRED_RANDOM_COVERAGE.items()
        },
        "simv": str(simv),
        "simv_sha256": sha256_file(simv),
        "spike": str(spike),
        "spike_sha256": sha256_file(spike),
        "generator_simv": str(generator_simv) if generator_simv is not None else None,
        "generator_simv_sha256": (
            sha256_file(generator_simv) if generator_simv is not None else None
        ),
        "source_snapshot": source_snapshot(),
        "jobs": args.jobs,
        "random_jobs": args.random_jobs,
        "seed": args.seed,
    }
    (output / "campaign.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    directed_output = output / "directed_apps"
    commands: List[Tuple[str, List[object], Path]] = [(
        "directed_apps",
        directed_command(directed_output, simv, args),
        output / "logs" / "directed_apps.log",
    )]
    for profile, _ in profiles:
        profile_output = output / "random" / profile
        commands.append((
            profile,
            random_command(profile, profile_output, simv, args),
            output / "logs" / f"{profile}.log",
        ))

    if args.dry_run:
        for name, command, _ in commands:
            print(f"{name}: {' '.join(str(part) for part in command)}")
        return 0

    components: Dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.random_jobs + 1) as executor:
        futures = {
            executor.submit(run_logged, name, command, log): name
            for name, command, log in commands
        }
        for future in as_completed(futures):
            name, returncode = future.result()
            components[name] = returncode

    coverage_paths = [
        output / "random" / profile / "stimulus_coverage.json"
        for profile, _ in profiles
    ]
    missing_coverage = [str(path) for path in coverage_paths if not path.is_file()]
    if missing_coverage:
        coverage: Dict[str, object] = {
            "status": "FAIL",
            "reason": f"missing random stimulus coverage reports: {missing_coverage}",
        }
        components["random_stimulus_coverage"] = 1
    else:
        coverage = merge_stimulus_coverage(coverage_paths)
        try:
            validate_random_stimulus_coverage(coverage, profiles)
        except RuntimeError as error:
            coverage["status"] = "FAIL"
            coverage["reason"] = str(error)
            components["random_stimulus_coverage"] = 1
        else:
            coverage["status"] = "PASS"
            components["random_stimulus_coverage"] = 0
    (output / "random_stimulus_coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    record_completed_source_snapshot(metadata, components, source_snapshot())

    rows = collect_results(output, profiles)
    all_pass = write_summary(output, rows, expected, components)
    complete = results_complete(rows, expected)
    metadata["status"] = "COMPLETE" if complete else "INCOMPLETE"
    metadata["verdict"] = (
        "PASS" if all_pass else
        ("FAIL" if complete else "INCOMPLETE")
    )
    metadata["completed_at"] = datetime.now().astimezone().isoformat()
    (output / "campaign.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
