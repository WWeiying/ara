#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from ara_verify.stimulus_coverage import merge_stimulus_coverage
from run_full_campaign import catalog_counts, random_profiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge a split/repaired full verification campaign")
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument(
        "--random-root",
        type=Path,
        action="append",
        default=[],
        help="random profile root in oldest-to-newest precedence order",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _read_array(path: Path) -> List[Dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"expected a JSON array in {path}")
    return value


def _suite_rows(campaign: Path) -> List[Dict[str, object]]:
    combined = campaign / "directed_apps" / "summary.json"
    split = [
        campaign / "directed_rvv" / "summary.json",
        campaign / "applications" / "summary.json",
    ]
    summaries = [combined] if combined.is_file() else split
    rows: List[Dict[str, object]] = []
    for summary in summaries:
        if not summary.is_file():
            continue
        for item in _read_array(summary):
            if item.get("status") == "DRY_RUN":
                continue
            rows.append({
                "class": item["kind"],
                "profile": "",
                "name": item["name"],
                "seed": "",
                "status": item["status"],
                "reason": item.get("reason", ""),
                "artifact_dir": item.get("artifact_dir", ""),
                "summary_source": str(summary),
            })
    return rows


def _random_item(
    profile: str, item: Dict[str, object], seed: int, source: Path
) -> Dict[str, object]:
    comparison = item.get("comparison", {})
    if not isinstance(comparison, dict):
        comparison = {}
    mismatch = comparison.get("mismatch", {})
    if not isinstance(mismatch, dict):
        mismatch = {}
    return {
        "class": "random",
        "profile": profile,
        "name": item["name"],
        "seed": seed,
        "status": item["status"],
        "reason": comparison.get("reason", "") or mismatch.get("reason", ""),
        "artifact_dir": item.get("artifact_dir", ""),
        "summary_source": str(source),
    }


def _profile_seed(profile: str, item: Dict[str, object], seed_start: int) -> int:
    match = re.fullmatch(rf"{re.escape(profile)}_(\d+)", str(item.get("name", "")))
    if match is not None:
        return seed_start + int(match.group(1))
    return int(item["seed"])


def _profile_results(root: Path, profile: str) -> Tuple[List[Dict[str, object]], Path] | None:
    profile_dir = root / profile
    summary = profile_dir / "summary.json"
    if summary.is_file():
        return _read_array(summary), summary
    case_results = sorted((profile_dir / "tests").glob(f"{profile}_*/result.json"))
    if case_results:
        return [json.loads(path.read_text(encoding="utf-8")) for path in case_results], profile_dir
    return None


def _random_rows(
    roots: Sequence[Path], profiles: Sequence[Tuple[str, int]], seed_start: int = 1
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    selected: Dict[str, str] = {}
    selected_profiles: Dict[str, str] = {}
    missing: Dict[str, int] = {}
    for profile, iterations in profiles:
        candidates = [result for root in roots if (result := _profile_results(root, profile))]
        selected_result = candidates[-1] if candidates else None
        items, source = selected_result if selected_result is not None else ([], None)
        by_seed = {_profile_seed(profile, item, seed_start): item for item in items}
        if source is not None:
            selected_profiles[profile] = str(source.parent if source.name == "summary.json" else source)
            if source.name == "summary.json":
                selected[profile] = str(source)
        for index in range(iterations):
            seed = seed_start + index
            item = by_seed.get(seed)
            if item is not None:
                rows.append(_random_item(profile, item, seed, source))
                continue
            missing[profile] = missing.get(profile, 0) + 1
            rows.append({
                "class": "random",
                "profile": profile,
                "name": f"{profile}_{index}",
                "seed": seed,
                "status": "NOT_RUN",
                "reason": "missing result",
                "artifact_dir": "",
                "summary_source": str(source) if source is not None else "",
            })
    return rows, {
        "selected_summaries": selected,
        "selected_profiles": selected_profiles,
        "missing_by_profile": missing,
    }


def collect(campaign: Path, random_roots: Sequence[Path]) -> Dict[str, object]:
    catalog = catalog_counts()
    profiles = random_profiles()
    expected = {
        "rvv": catalog["rvv"],
        "app": catalog["app"],
        "random": sum(iterations for _, iterations in profiles),
    }
    expected["total"] = sum(expected.values())
    suite_rows = _suite_rows(campaign)
    random_rows, random_meta = _random_rows(random_roots, profiles)
    rows = suite_rows + random_rows
    class_counts = Counter(str(row["class"]) for row in rows)
    status_counts = Counter(str(row["status"]) for row in rows)
    inventory_complete = all(class_counts[name] == expected[name] for name in ("rvv", "app", "random"))
    execution_complete = inventory_complete and status_counts["NOT_RUN"] == 0
    coverage_paths = [
        Path(profile_dir) / "stimulus_coverage.json"
        for profile_dir in random_meta["selected_profiles"].values()
    ]
    missing_coverage = [str(path) for path in coverage_paths if not path.is_file()]
    coverage = merge_stimulus_coverage(
        [path for path in coverage_paths if path.is_file()]
    )
    coverage["missing_profiles"] = [
        profile
        for profile, _ in profiles
        if profile not in random_meta["selected_profiles"]
    ]
    coverage["missing_reports"] = missing_coverage
    return {
        "status": "COMPLETE" if execution_complete else "INCOMPLETE",
        "collected_at": datetime.now().astimezone().isoformat(),
        "campaign": str(campaign),
        "random_roots": [str(root) for root in random_roots],
        "expected": expected,
        "observed": {"total": len(rows), "by_class": dict(sorted(class_counts.items()))},
        "status_counts": dict(sorted(status_counts.items())),
        "random_selection": random_meta,
        "random_stimulus_coverage": coverage,
        "results": rows,
    }


def write(payload: Dict[str, object], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "full_campaign_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "full_campaign_coverage.json").write_text(
        json.dumps(payload["random_stimulus_coverage"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fields = [
        "class", "profile", "name", "seed", "status", "reason", "artifact_dir",
        "summary_source",
    ]
    with (output / "full_campaign_summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(payload["results"])


def main() -> int:
    args = parse_args()
    campaign = args.campaign.resolve()
    roots = [campaign / "random", *(root.resolve() for root in args.random_root)]
    output = args.output.resolve() if args.output else campaign / "merged"
    payload = collect(campaign, roots)
    write(payload, output)
    print(json.dumps({
        "status": payload["status"],
        "expected": payload["expected"],
        "observed": payload["observed"],
        "status_counts": payload["status_counts"],
        "output": str(output),
    }, indent=2, sort_keys=True))
    return 0 if payload["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
