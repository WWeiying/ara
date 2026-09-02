#!/usr/bin/env python3
"""Aggregate strict Prefill Attention evidence across a real-capture matrix."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import analyze_prefill_attention as single_case


DEFAULT_REQUIRED_M = (15, 64, 128, 256, 512, 1024)
DEFAULT_REQUIRED_P = (0, 512, 2048)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_positive_set(value: str) -> tuple[int, ...]:
    try:
        result = tuple(sorted({int(item) for item in value.split(",") if item}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("values must be comma-separated integers") from error
    if not result or any(item < 0 for item in result):
        raise argparse.ArgumentTypeError("values must be non-negative integers")
    return result


def reference_index(path: Path | None) -> tuple[dict[str, dict], dict]:
    if path is None:
        return {}, {"status": "NOT_PROVIDED", "report": None}
    path = path.resolve()
    report = load_json(path)
    entries: dict[str, dict] = {}
    for entry in report.get("cases", []):
        case_id = entry.get("case_id")
        if not case_id or case_id in entries:
            raise ValueError(f"{path}: missing or duplicate reference case_id")
        entries[case_id] = entry
    return entries, {
        "status": report.get("status", "UNKNOWN"),
        "report": str(path),
        "report_sha256": sha256(path),
        "reference": report.get("reference"),
        "case_count": report.get("case_count"),
        "failed_cases": report.get("failed_cases"),
    }


def strategy_map(summary: dict) -> dict[str, dict]:
    return {entry["name"]: entry for entry in summary["strategies"]}


def case_row(entry: dict, summary: dict, reference: dict | None) -> dict:
    shape = summary["shape"]
    work = summary["work"]
    payload = summary["payload"]
    q2 = summary["kv_outer_q2_exact"]
    panel = summary["kv_outer_q2_panel4_exact"]
    strategies = strategy_map(summary)
    row = {
        "case_id": entry["id"],
        "P": shape["past_tokens"],
        "M": shape["query_tokens"],
        "D": shape["head_dim"],
        "Hq": shape["query_heads"],
        "Hkv": shape["kv_heads"],
        "GQA": shape["gqa_rows"],
        "kv_capacity": shape["kv_capacity"],
        "attention_macs": work["attention_macs"],
        "query_f32_bytes": payload["query_f32_bytes"],
        "mask_physical_bytes": payload["mask_physical_bytes"],
        "output_f32_bytes": payload["output_f32_bytes"],
        "unique_visible_kv_bytes": payload["unique_visible_kv_bytes"],
        "ordinary_rvv_kv_bytes": strategies["rvv_qhead_serial"]["external_kv_bytes"],
        "tiled_rvv_q4_kv_bytes": strategies["rvv_gqa_q4"]["external_kv_bytes"],
        "serial_akv_kv_bytes": strategies["akv_gqa_serial"]["external_kv_bytes"],
        "q2_external_kv_bytes": q2["external_kv_bytes"],
        "q2_replay_bytes": q2["replay_bytes"],
        "q2_command_records": q2["command_records"],
        "panel4_external_kv_bytes": panel["external_kv_bytes"],
        "panel4_replay_bytes": panel["replay_bytes"],
        "panel4_command_records": panel["command_records"],
        "panel4_column_commands": panel["v2_column_panel"],
        "panel4_logical_columns": panel["v2_logical_column"],
        "panel4_k_view_bank_cycles": panel["v2_k_view_bank_cycles"],
        "case_sha256": summary["provenance"]["case_sha256"],
        "reference_status": "NOT_PROVIDED",
        "reference_mismatches": None,
        "reference_max_abs_error": None,
    }
    if reference is not None:
        if reference.get("case_sha256") != row["case_sha256"]:
            raise ValueError(f"{entry['id']}: reference report case hash mismatch")
        row.update({
            "reference_status": reference.get("status", "UNKNOWN"),
            "reference_mismatches": reference.get("mismatches"),
            "reference_max_abs_error": reference.get("max_abs_error", {}).get("value"),
        })
    return row


def analyze_matrix(
    root: Path,
    query_tiles: list[int],
    required_m: tuple[int, ...] = DEFAULT_REQUIRED_M,
    required_p: tuple[int, ...] = DEFAULT_REQUIRED_P,
    reference_report: Path | None = None,
) -> dict:
    root = root.resolve()
    manifest_path = root / "replay" / "manifest.json"
    manifest = load_json(manifest_path)
    references, reference_summary = reference_index(reference_report)
    rows = []
    seen_ids: set[str] = set()
    seen_shapes: set[tuple[int, int]] = set()
    for entry in manifest.get("cases", []):
        case_id = entry.get("id")
        if not case_id or case_id in seen_ids:
            raise ValueError(f"{manifest_path}: missing or duplicate case id")
        seen_ids.add(case_id)
        case_path = (root / entry["path"] / "case.json").resolve()
        summary = single_case.analyze(case_path, query_tiles)
        row = case_row(entry, summary, references.get(case_id))
        key = (row["P"], row["M"])
        if key in seen_shapes:
            raise ValueError(f"duplicate Prefill matrix shape P={key[0]}, M={key[1]}")
        seen_shapes.add(key)
        rows.append(row)

    unknown_references = sorted(set(references) - seen_ids)
    missing_references = sorted(seen_ids - set(references)) if references else []
    if unknown_references:
        raise ValueError(
            "reference report contains cases outside the capture manifest: "
            + ", ".join(unknown_references)
        )
    missing_combinations = [
        {"P": past, "M": tokens}
        for past in required_p
        for tokens in required_m
        if (past, tokens) not in seen_shapes
    ]
    failed_reference_cases = sorted(
        row["case_id"] for row in rows
        if references and row["reference_status"] != "PASS"
    )
    matrix_status = "PASS" if not missing_combinations else "INCOMPLETE"
    if not references:
        bound_reference_status = "NOT_PROVIDED"
    elif missing_references or failed_reference_cases or reference_summary["status"] != "PASS":
        bound_reference_status = "FAIL"
    else:
        bound_reference_status = "PASS"
    overall_status = (
        "PASS"
        if matrix_status == "PASS" and bound_reference_status == "PASS"
        else "INCOMPLETE"
    )
    return {
        "schema_version": 1,
        "status": overall_status,
        "scope": "real llama.cpp Prefill Attention matrix evidence",
        "capture_root": str(root),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "required_M": list(required_m),
        "required_P": list(required_p),
        "required_combination_count": len(required_m) * len(required_p),
        "observed_case_count": len(rows),
        "matrix_status": matrix_status,
        "missing_combinations": missing_combinations,
        "reference": {
            **reference_summary,
            "bound_status": bound_reference_status,
            "missing_cases": missing_references,
            "failed_cases": failed_reference_cases,
        },
        "cases": sorted(rows, key=lambda row: (row["P"], row["M"])),
    }


def write_outputs(summary: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    rows = summary["cases"]
    with (output_dir / "cases.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    with (output_dir / "missing_combinations.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=["P", "M"])
        writer.writeheader()
        writer.writerows(summary["missing_combinations"])
    (output_dir / "analysis.done").write_text(summary["status"] + "\n", encoding="ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--query-tiles", type=single_case.parse_query_tiles, default=[2, 4])
    parser.add_argument("--required-m", type=parse_positive_set, default=DEFAULT_REQUIRED_M)
    parser.add_argument("--required-p", type=parse_positive_set, default=DEFAULT_REQUIRED_P)
    parser.add_argument("--reference-report", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    summary = analyze_matrix(
        args.capture_root,
        args.query_tiles,
        args.required_m,
        args.required_p,
        args.reference_report,
    )
    write_outputs(summary, args.output_dir)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" or args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
