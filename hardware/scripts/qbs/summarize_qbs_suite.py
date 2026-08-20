#!/usr/bin/env python3
"""Merge completed per-case QBS evaluation CSV files into suite tables."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


TABLES = {
    "results.csv": "result.csv",
    "qbs_perf.csv": "qbs_perf.csv",
    "metrics.csv": "metrics.csv",
}


def read_manifest(path: Path) -> list[tuple[str, Path]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise RuntimeError(f"empty manifest: {path}")
    return [(row["case"], Path(row["run_dir"])) for row in rows]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    cases = read_manifest(run_root / "manifest.tsv")
    complete: list[tuple[str, Path]] = []
    incomplete: list[str] = []
    for case, run_dir in cases:
        status_file = run_dir / "status"
        if status_file.is_file() and status_file.read_text().strip() == "PASS":
            complete.append((case, run_dir))
        else:
            incomplete.append(case)
    if incomplete and not args.allow_partial:
        raise SystemExit("incomplete or failed cases: " + ", ".join(incomplete))
    if not complete:
        raise SystemExit("no passing QBS cases to summarize")

    for output_name, input_name in TABLES.items():
        rows: list[dict[str, str]] = []
        for case, run_dir in complete:
            path = run_dir / input_name
            if not path.is_file():
                raise SystemExit(f"{case}: missing {path}")
            rows.extend(read_rows(path))
        write_rows(run_root / output_name, rows)
        print(f"wrote {run_root / output_name} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
