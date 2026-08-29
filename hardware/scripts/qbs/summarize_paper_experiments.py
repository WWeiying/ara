#!/usr/bin/env python3
"""Strictly summarize the production-path QBS paper experiments."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "llama_qwen25_real"))

from summarize_format_closure import (  # noqa: E402
    check_metrics,
    check_pair,
    check_provenance_pair,
    check_qbs_perf,
    file_sha256,
    number,
    read_one,
    read_phase,
    read_provenance,
    require_pass,
)


OPERATORS = (
    ("Decode Attn-Q", "decode_attn_q_eval", "operator_decode_attn_q"),
    ("Decode FFN-Gate", "decode_ffn_gate_eval", "operator_decode_ffn_gate"),
    ("Decode FFN-Down", "decode_ffn_down_eval", "operator_decode_ffn_down"),
    ("Prefill Attn-Q", "prefill_attn_q_eval", "operator_prefill_attn_q"),
    ("Prefill FFN-Gate", "prefill_ffn_gate_eval", "operator_prefill_ffn_gate"),
    ("Prefill FFN-Down", "prefill_ffn_down_eval", "operator_prefill_ffn_down"),
)


def geometric_mean(values: list[float]) -> float:
    if not values or any(value <= 0 for value in values):
        raise RuntimeError("geometric mean requires positive values")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise RuntimeError("ratio denominator must be positive")
    return numerator / denominator


def require_root_pass(root: Path) -> None:
    status = root / "status"
    done = root / "DONE"
    if not done.is_file() or not status.is_file() or status.read_text().strip() != "PASS":
        raise RuntimeError(f"experiment root is not complete and PASS: {root}")


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise RuntimeError(f"missing provenance artifact: {path}")
    return path


def verify_single_sha256_manifest(path: Path) -> None:
    fields = path.read_text().strip().split(maxsplit=1)
    if len(fields) != 2:
        raise RuntimeError(f"malformed SHA-256 manifest: {path}")
    expected, filename = fields
    artifact = Path(filename.lstrip("* "))
    if not artifact.is_absolute():
        artifact = path.parent / artifact
    artifact = require_file(artifact)
    if file_sha256(artifact) != expected:
        raise RuntimeError(f"SHA-256 manifest mismatch: {artifact}")


def require_production(qbs_result: dict[str, str], provenance: dict[str, object]) -> None:
    if provenance.get("qbs_descriptor_mode") != "per_command_stack_in_timed_region":
        raise RuntimeError(f"not a production descriptor path: {qbs_result.get('case')}")
    if provenance.get("qbs_command_setup_in_timed_region") is not True:
        raise RuntimeError(f"command setup is not in timed region: {qbs_result.get('case')}")
    if qbs_result.get("timing_scope") != "production_command":
        raise RuntimeError(f"unexpected timing scope: {qbs_result.get('case')}")
    if number(qbs_result, "setup_included") != 1:
        raise RuntimeError(f"result excludes setup: {qbs_result.get('case')}")
    if number(qbs_result, "timed_cycles") != number(qbs_result, "compute_cycles"):
        raise RuntimeError(
            f"production timing fields disagree: {qbs_result.get('case')}"
        )


def paired_row(label: str, rvv_dir: Path, qbs_dir: Path) -> dict[str, object]:
    require_pass(rvv_dir)
    require_pass(qbs_dir)
    rvv = read_one(rvv_dir / "result.csv")
    qbs = read_one(qbs_dir / "result.csv")
    rvv_metrics = read_phase(rvv_dir / "metrics.csv", "total")
    qbs_metrics = read_phase(qbs_dir / "metrics.csv", "total")
    qbs_perf = read_one(qbs_dir / "qbs_perf.csv")
    check_pair(rvv, qbs)
    check_metrics(rvv, rvv_metrics)
    check_metrics(qbs, qbs_metrics)
    check_qbs_perf(qbs, qbs_perf)
    rvv_provenance = read_provenance(rvv_dir / "provenance.json")
    qbs_provenance = read_provenance(qbs_dir / "provenance.json")
    signatures = check_provenance_pair(rvv_provenance, qbs_provenance)
    require_production(qbs, qbs_provenance)

    # RVV's compute interval and QBS's timed interval begin before activation
    # quantization and end after result stores.  The latter additionally
    # includes per-command descriptor construction and command setup.
    rvv_timed = number(rvv, "compute_cycles")
    qbs_timed = number(qbs, "timed_cycles")
    rvv_matmul = number(rvv, "matmul_cycles")
    qbs_matmul = number(qbs, "matmul_cycles")
    row: dict[str, object] = {
        "workload": label,
        "operator": rvv_provenance["operator"],
        "phase": rvv_provenance["phase"],
        "format": rvv_provenance["weight_type"],
        "k": number(rvv, "k"),
        "n": number(rvv, "rows"),
        "m": number(rvv, "inputs"),
        "rvv_timed_cycles": rvv_timed,
        "qbs_timed_cycles": qbs_timed,
        "operator_speedup": ratio(rvv_timed, qbs_timed),
        "rvv_quantize_cycles": number(rvv, "quantize_cycles"),
        "qbs_quantize_cycles": number(qbs, "quantize_cycles"),
        "rvv_pack_cycles": number(rvv, "pack_cycles"),
        "qbs_pack_cycles": number(qbs, "pack_cycles"),
        "rvv_matmul_cycles": rvv_matmul,
        "qbs_matmul_cycles": qbs_matmul,
        "matmul_speedup": ratio(rvv_matmul, qbs_matmul),
        "rvv_retired_inst_count": number(rvv_metrics, "retired_inst_count"),
        "qbs_retired_inst_count": number(qbs_metrics, "retired_inst_count"),
        "rvv_axi_r_bus_bytes": number(rvv_metrics, "axi_r_bus_bytes"),
        "qbs_axi_r_bus_bytes": number(qbs_metrics, "axi_r_bus_bytes"),
        "rvv_simv_sha256": file_sha256(rvv_dir / "simv"),
        "qbs_simv_sha256": file_sha256(qbs_dir / "simv"),
        "rvv_elf_sha256": file_sha256(rvv_dir / "benchmark.elf"),
        "qbs_elf_sha256": file_sha256(qbs_dir / "benchmark.elf"),
        "qbs_descriptor_mode": qbs_provenance["qbs_descriptor_mode"],
        "qbs_command_setup_in_timed_region": True,
        "qbs_runtime_timed_region": qbs_provenance["runtime_timed_region"],
    }
    row.update(signatures)
    for field, value in qbs_perf.items():
        if field != "case":
            row[f"qbs_{field}"] = value
    return row


def qbs_comparison_row(
    label: str,
    reference_dir: Path,
    variant_dir: Path,
    reference_name: str,
    variant_name: str,
) -> dict[str, object]:
    require_pass(reference_dir)
    require_pass(variant_dir)
    reference = read_one(reference_dir / "result.csv")
    variant = read_one(variant_dir / "result.csv")
    check_pair(reference, variant)
    ref_prov = read_provenance(reference_dir / "provenance.json")
    var_prov = read_provenance(variant_dir / "provenance.json")
    check_provenance_pair(ref_prov, var_prov)
    ref_perf = read_one(reference_dir / "qbs_perf.csv")
    var_perf = read_one(variant_dir / "qbs_perf.csv")
    check_qbs_perf(reference, ref_perf)
    check_qbs_perf(variant, var_perf)
    row: dict[str, object] = {
        "workload": label,
        "format": ref_prov["weight_type"],
        "k": number(reference, "k"),
        "n": number(reference, "rows"),
        "m": number(reference, "inputs"),
        f"{reference_name}_compute_cycles": number(reference, "compute_cycles"),
        f"{variant_name}_compute_cycles": number(variant, "compute_cycles"),
        f"{reference_name}_matmul_cycles": number(reference, "matmul_cycles"),
        f"{variant_name}_matmul_cycles": number(variant, "matmul_cycles"),
        f"{reference_name}_simv_sha256": file_sha256(reference_dir / "simv"),
        f"{variant_name}_simv_sha256": file_sha256(variant_dir / "simv"),
    }
    for field, value in ref_perf.items():
        if field != "case":
            row[f"{reference_name}_{field}"] = value
    for field, value in var_perf.items():
        if field != "case":
            row[f"{variant_name}_{field}"] = value
    return row


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty result: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rvv-operator-root", type=Path, required=True)
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-git-head", required=True)
    args = parser.parse_args()

    rvv_root = args.rvv_operator_root.resolve()
    experiment_root = args.experiment_root.resolve()
    runs = experiment_root / "runs"
    require_root_pass(experiment_root)
    provenance_dir = experiment_root / "provenance"
    rvv_head = require_file(rvv_root / "git_head").read_text().strip()
    main_head = require_file(provenance_dir / "main_git_head").read_text().strip()
    extra_head = require_file(provenance_dir / "extra_git_head").read_text().strip()
    nolook_head = require_file(provenance_dir / "nolook_git_head").read_text().strip()
    for name, value in (
        ("RVV", rvv_head),
        ("experiment runner", main_head),
        ("production QBS", extra_head),
        ("no-lookahead QBS", nolook_head),
    ):
        if value != args.expected_git_head:
            raise RuntimeError(
                f"{name} revision mismatch: expected {args.expected_git_head}, got {value}"
            )

    provenance_files = (
        ("main_git_diff", require_file(provenance_dir / "main_git_diff.patch")),
        ("extra_git_diff", require_file(provenance_dir / "extra_git_diff.patch")),
        (
            "extra_shape_sources",
            require_file(provenance_dir / "extra_shape_sources.sha256"),
        ),
        (
            "extra_shape_source_archive",
            require_file(provenance_dir / "extra_shape_sources.tar"),
        ),
        (
            "extra_shape_source_archive_manifest",
            require_file(provenance_dir / "extra_shape_sources.tar.sha256"),
        ),
        ("nolook_git_diff", require_file(provenance_dir / "nolook_git_diff.patch")),
        ("runner_scripts", require_file(provenance_dir / "runner_scripts.sha256")),
        ("qbs_1m_simv", require_file(provenance_dir / "qbs_1m_simv.sha256")),
        (
            "qbs_1m_simv_daidir",
            require_file(provenance_dir / "qbs_1m_simv_daidir.sha256"),
        ),
        ("rvv_1m_simv", require_file(provenance_dir / "rvv_1m_simv.sha256")),
        (
            "rvv_1m_simv_daidir",
            require_file(provenance_dir / "rvv_1m_simv_daidir.sha256"),
        ),
        ("qbs_16m_simv", require_file(provenance_dir / "qbs_16m_simv.sha256")),
        (
            "qbs_16m_simv_daidir",
            require_file(provenance_dir / "qbs_16m_simv_daidir.sha256"),
        ),
        (
            "nolookahead_qbs_1m_simv",
            require_file(provenance_dir / "nolookahead_qbs_1m_simv.sha256"),
        ),
        (
            "nolookahead_qbs_1m_simv_daidir",
            require_file(
                provenance_dir / "nolookahead_qbs_1m_simv_daidir.sha256"
            ),
        ),
    )
    provenance_rows = [
        {
            "artifact": name,
            "path": str(path),
            "sha256": file_sha256(path),
        }
        for name, path in provenance_files
    ]
    verify_single_sha256_manifest(
        provenance_dir / "extra_shape_sources.tar.sha256"
    )
    for name in ("qbs_1m", "rvv_1m", "qbs_16m", "nolookahead_qbs_1m"):
        verify_single_sha256_manifest(provenance_dir / f"{name}_simv.sha256")

    operator_rows = [
        paired_row(label, rvv_root / rvv_case, runs / qbs_case)
        for label, rvv_case, qbs_case in OPERATORS
    ]

    shape_specs = (
        ("Decode", 32, runs / "shape_decode_n32_rvv", runs / "shape_decode_n32_qbs"),
        ("Decode", 256, runs / "shape_decode_n256_rvv", runs / "shape_decode_n256_qbs"),
        ("Decode", 1536, rvv_root / "decode_attn_q_eval", runs / "operator_decode_attn_q"),
        ("Prefill", 32, runs / "shape_prefill_n32_rvv", runs / "focused_q4_m4_n32"),
        ("Prefill", 256, runs / "shape_prefill_n256_rvv", runs / "shape_prefill_n256_qbs"),
        ("Prefill", 1536, rvv_root / "prefill_attn_q_eval", runs / "operator_prefill_attn_q"),
    )
    shape_rows = []
    for phase, expected_n, rvv_dir, qbs_dir in shape_specs:
        row = paired_row(f"{phase} N={expected_n}", rvv_dir, qbs_dir)
        if int(row["n"]) != expected_n:
            raise RuntimeError(f"shape point has unexpected N: {row}")
        shape_rows.append(row)

    production = runs / "shape_decode_n32_qbs"
    prebuilt = runs / "shape_decode_n32_qbs_prebuilt"
    descriptor_rows = [
        qbs_comparison_row(
            "Decode N=32", production, prebuilt, "production", "prebuilt"
        ),
        qbs_comparison_row(
            "Decode N=1536",
            runs / "operator_decode_attn_q",
            runs / "shape_decode_n1536_qbs_prebuilt",
            "production",
            "prebuilt",
        ),
    ]
    production_result = read_one(production / "result.csv")
    require_production(
        production_result, read_provenance(production / "provenance.json")
    )
    for prebuilt_dir in (
        prebuilt,
        runs / "shape_decode_n1536_qbs_prebuilt",
    ):
        current_result = read_one(prebuilt_dir / "result.csv")
        prebuilt_provenance = read_provenance(prebuilt_dir / "provenance.json")
        if prebuilt_provenance.get("qbs_descriptor_mode") != "prebuilt_before_timed_region":
            raise RuntimeError("descriptor ablation is not the prebuilt path")
        if prebuilt_provenance.get("qbs_command_setup_in_timed_region") is not False:
            raise RuntimeError("prebuilt descriptor unexpectedly reports setup in timing")
        if current_result.get("timing_scope") != "prebuilt_descriptor":
            raise RuntimeError("prebuilt result has unexpected timing scope")

    lookahead_rows = [
        qbs_comparison_row(
            "Q3_K Decode Attn-Q",
            runs / "focused_q3_m1",
            runs / "nolookahead_q3_m1",
            "lookahead_on",
            "lookahead_off",
        ),
        qbs_comparison_row(
            "Q6_K Decode Attn-Q",
            runs / "format_q6_m1",
            runs / "nolookahead_q6_m1",
            "lookahead_on",
            "lookahead_off",
        ),
    ]
    for row in lookahead_rows:
        row["matmul_speedup_from_lookahead"] = ratio(
            int(row["lookahead_off_matmul_cycles"]),
            int(row["lookahead_on_matmul_cycles"]),
        )

    out = args.output_dir.resolve()
    write_csv(out / "operator_closure.csv", operator_rows)
    write_csv(out / "shape_closure.csv", shape_rows)
    write_csv(out / "descriptor_ablation.csv", descriptor_rows)
    write_csv(out / "lookahead_ablation.csv", lookahead_rows)
    write_csv(out / "provenance.csv", provenance_rows)

    operator_speedup = geometric_mean(
        [float(row["operator_speedup"]) for row in operator_rows]
    )
    operator_matmul = geometric_mean(
        [float(row["matmul_speedup"]) for row in operator_rows]
    )
    summary = [
        "# QBS production-path paper experiment closure",
        "",
        f"Source revision: `{args.expected_git_head}`.",
        "The exact dirty-worktree deltas and runner hashes are frozen in "
        "`provenance.csv`; the results must not be described as commit-only data.",
        "Every primary QBS point includes per-command descriptor construction, "
        "fence/vset setup, blocking execution, and result stores in the timed region.",
        "Persistent model-load weight repacking is excluded from both paths.",
        "",
        f"Six-operator geometric mean: {operator_speedup:.3f}x full timed-region and "
        f"{operator_matmul:.3f}x matrix-phase speedup.",
        "",
        "The shape, descriptor, and lookahead CSV files are controlled comparisons; "
        "their interpretation must follow the measured counters rather than a preset claim.",
        "",
    ]
    (out / "README.md").write_text("\n".join(summary), encoding="utf-8")
    print(f"wrote strict production-path closure to {out}")


if __name__ == "__main__":
    main()
