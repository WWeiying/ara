#!/usr/bin/env python3

"""Select real-model QBS shapes by conservative projected RTL cycles."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from context_sweep import load_json, sha256


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CALIBRATION = Path(__file__).with_name("qbs-cycle-calibration.json")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def qbs_signature(summary: dict[str, object]) -> Counter[tuple[object, ...]]:
    return Counter(
        (
            row.get("operation", "MUL_MAT"), row["profile"],
            int(row["k"]), int(row["m"]), int(row["n"]),
            int(row["dot_elements"]), int(row["weight_bytes"]),
            int(row.get("weight_unique_tensor_bytes", row["weight_bytes"])),
            int(row["activation_bytes"]),
            str(row["name"]),
        )
        for row in summary["decode"]["qbs_shapes"]
    )


def collect_shapes(input_root: Path) -> tuple[list[dict[str, object]], list[str], list[int]]:
    if (input_root / "complete").read_text().strip() != "PASS":
        raise ValueError(f"incomplete context sweep: {input_root}")
    with (input_root / "dynamic_counts.csv").open(newline="", encoding="utf-8") as stream:
        dynamic_rows = list(csv.DictReader(stream))
    if not dynamic_rows or any(row["status"] != "PASS" for row in dynamic_rows):
        raise ValueError("context sweep contains a missing or failed point")
    models = sorted({row["model"] for row in dynamic_rows})
    kv_lengths = sorted({int(row["effective_kv"]) for row in dynamic_rows})
    if len(dynamic_rows) != len(models) * len(kv_lengths):
        raise ValueError("context sweep is not a complete model/KV matrix")

    aggregate: dict[tuple[str, str, int, int, int, int], dict[str, object]] = defaultdict(
        lambda: {
            "nodes": 0,
            "dot_elements": 0,
            "weight_logical_bytes": 0,
            "activation_elements": 0,
            "models": set(),
        }
    )
    for model in models:
        summaries = []
        for kv in kv_lengths:
            path = input_root / model / f"kv{kv}" / "summary.json"
            if not path.is_file():
                raise FileNotFoundError(path)
            summaries.append(load_json(path))
        reference_signature = qbs_signature(summaries[0])
        for summary in summaries[1:]:
            if qbs_signature(summary) != reference_signature:
                raise ValueError(f"QBS Decode shapes vary with KV for {model}")
        for row in summaries[0]["decode"]["qbs_shapes"]:
            activation_rows = int(row.get("activation_rows", row["m"]))
            key = (
                str(row.get("operation", "MUL_MAT")), str(row["profile"]),
                int(row["k"]), int(row["m"]), int(row["n"]), activation_rows,
            )
            record = aggregate[key]
            record["nodes"] = int(record["nodes"]) + 1
            record["dot_elements"] = int(record["dot_elements"]) + int(row["dot_elements"])
            record["weight_logical_bytes"] = (
                int(record["weight_logical_bytes"]) + int(row["weight_bytes"])
            )
            record["activation_elements"] = (
                int(record["activation_elements"]) + int(row["k"]) * activation_rows
            )
            record["models"].add(model)

    rows = []
    for (operation, profile, k, m, n, activation_rows), record in aggregate.items():
        rows.append({
            "operation": operation,
            "profile": profile,
            "k": k,
            "m": m,
            "n": n,
            "activation_rows": activation_rows,
            "nodes": record["nodes"],
            "dot_elements": record["dot_elements"],
            "weight_logical_bytes": record["weight_logical_bytes"],
            "activation_elements": record["activation_elements"],
            "models": "/".join(sorted(record["models"])),
        })
    return rows, models, kv_lengths


def project(rows: list[dict[str, object]], calibration: dict[str, object]) -> None:
    profiles = calibration["profiles"]
    for row in rows:
        profile = str(row["profile"])
        if profile not in profiles:
            raise ValueError(f"no calibration for {profile}")
        point = profiles[profile]
        matmul_rate = float(point["matmul_cycles"]) / int(point["matmul_weight_logical_bytes"])
        quantize_rate = float(point["quantize_cycles"]) / int(point["quantize_activation_elements"])
        matmul_cycles = int(row["weight_logical_bytes"]) * matmul_rate
        quantize_cycles = int(row["activation_elements"]) * quantize_rate
        row["matmul_projected_cycles"] = round(matmul_cycles)
        row["quantize_projected_cycles_no_reuse"] = round(quantize_cycles)
        row["projected_cycles_no_reuse"] = round(matmul_cycles + quantize_cycles)
        row["calibration_kind"] = point["calibration_kind"]


def select(rows: list[dict[str, object]], target: float) -> tuple[list[dict[str, object]], float]:
    ranked = sorted(rows, key=lambda row: int(row["projected_cycles_no_reuse"]), reverse=True)
    total = sum(int(row["projected_cycles_no_reuse"]) for row in ranked)
    cumulative = 0
    selected = []
    for rank, row in enumerate(ranked, 1):
        cycles = int(row["projected_cycles_no_reuse"])
        cumulative += cycles
        row["rank"] = rank
        row["cycle_share"] = cycles / total
        row["cumulative_cycle_share"] = cumulative / total
        row["selected"] = int(cumulative - cycles < target * total)
        if row["selected"]:
            selected.append(row)
    return selected, sum(int(row["projected_cycles_no_reuse"]) for row in selected) / total


def sensitivity_coverage(
    rows: list[dict[str, object]], selected: list[dict[str, object]], profile: str, multipliers: list[float]
) -> list[dict[str, float]]:
    selected_keys = {
        (
            row["operation"], row["profile"], row["k"], row["m"], row["n"],
            row.get("activation_rows", row["m"]),
        )
        for row in selected
    }
    results = []
    for multiplier in multipliers:
        total = 0.0
        covered = 0.0
        for row in rows:
            cycles = float(row["projected_cycles_no_reuse"])
            if row["profile"] == profile:
                cycles *= multiplier
            total += cycles
            if (
                row["operation"], row["profile"], row["k"], row["m"], row["n"],
                row.get("activation_rows", row["m"]),
            ) in selected_keys:
                covered += cycles
        results.append({"multiplier": multiplier, "coverage": covered / total})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    input_root = args.input.resolve()
    output = (args.output or input_root / "qbs_representative_selection").resolve()
    output.mkdir(parents=True, exist_ok=False)
    calibration = load_json(args.calibration)
    if int(calibration.get("schema_version", 0)) != 1:
        raise ValueError("unsupported QBS calibration schema")

    rows, models, kv_lengths = collect_shapes(input_root)
    project(rows, calibration)
    target = float(calibration["coverage_target"])
    selected, nominal_coverage = select(rows, target)
    sensitivity = calibration["sensitivity"]
    sensitivity_rows = sensitivity_coverage(
        rows, selected, str(sensitivity["profile"]),
        [float(value) for value in sensitivity["total_cycle_multipliers"]],
    )
    minimum = min(row["coverage"] for row in sensitivity_rows)
    if nominal_coverage < target or minimum < float(calibration["minimum_sensitivity_coverage"]):
        raise ValueError("representative set does not meet its coverage contract")

    ordered = sorted(rows, key=lambda row: int(row["rank"]))
    columns = [
        "rank", "selected", "operation", "profile", "k", "m", "n",
        "activation_rows", "nodes", "models",
        "dot_elements", "weight_logical_bytes", "activation_elements",
        "matmul_projected_cycles", "quantize_projected_cycles_no_reuse",
        "projected_cycles_no_reuse", "cycle_share", "cumulative_cycle_share",
        "calibration_kind",
    ]
    write_csv(output / "all_shapes.csv", [{key: row[key] for key in columns} for row in ordered])
    write_csv(output / "selected_shapes.csv", [{key: row[key] for key in columns} for row in selected])
    write_csv(output / "sensitivity.csv", sensitivity_rows)

    result = {
        "schema_version": 1,
        "baseline_commit": calibration["baseline_commit"],
        "scope": calibration["scope"],
        "models": models,
        "model_trace_multiplicity": {model: 1 for model in models},
        "validated_kv_lengths": kv_lengths,
        "qbs_shapes_are_kv_invariant": True,
        "coverage_target": target,
        "selected_shape_count": len(selected),
        "nominal_coverage": nominal_coverage,
        "minimum_sensitivity_coverage": minimum,
        "sensitivity_profile": sensitivity["profile"],
        "input_dynamic_counts_sha256": sha256(input_root / "dynamic_counts.csv"),
        "input_provenance_sha256": sha256(input_root / "provenance.json"),
        "calibration_sha256": sha256(args.calibration),
    }
    (output / "selection.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# QBS Representative Shape Selection",
        "",
        f"- Scope: {calibration['scope']}.",
        f"- Models: {', '.join(models)} (one Decode graph each; projected work is pooled).",
        f"- KV lengths checked for shape invariance: {', '.join(map(str, kv_lengths))}.",
        f"- Selected {len(selected)} shapes; nominal coverage: {nominal_coverage:.3%}.",
        f"- Minimum Q5_0 sensitivity coverage: {minimum:.3%}.",
        "- Projected cycles are a conservative ranking metric, not measured model cycles.",
        "",
        "| Rank | Operation | Profile | K | M | A rows | N | Nodes | Projected cycles | Cumulative |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in selected:
        lines.append(
            f"| {row['rank']} | {row['operation']} | {row['profile']} | "
            f"{row['k']} | {row['m']} | {row['activation_rows']} | {row['n']} | "
            f"{row['nodes']} | {row['projected_cycles_no_reuse']} | "
            f"{float(row['cumulative_cycle_share']):.3%} |"
        )
    (output / "README.md").write_text("\n".join(lines) + "\n")
    (output / "complete").write_text("PASS\n", encoding="ascii")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
