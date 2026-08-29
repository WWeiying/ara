#!/usr/bin/env python3
"""Strictly pair the six real-model RVV and QBS operator-slice runs."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from summarize_format_closure import (
    check_metrics,
    check_pair,
    check_provenance_pair,
    check_qbs_perf,
    file_sha256,
    number,
    read_one,
    read_phase,
    read_provenance,
    read_root_value,
    require_pass,
)


CASES = (
    ("Decode Attn-Q", "decode_attn_q_eval", "decode_attn_q_qbs"),
    ("Decode FFN-Gate", "decode_ffn_gate_eval", "decode_ffn_gate_qbs"),
    ("Decode FFN-Down", "decode_ffn_down_eval", "decode_ffn_down_qbs"),
    ("Prefill Attn-Q", "prefill_attn_q_eval", "prefill_attn_q_qbs"),
    ("Prefill FFN-Gate", "prefill_ffn_gate_eval", "prefill_ffn_gate_qbs"),
    ("Prefill FFN-Down", "prefill_ffn_down_eval", "prefill_ffn_down_qbs"),
)


def ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        raise RuntimeError("zero denominator in paired result")
    return numerator / denominator


def geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(value) for value in values) / len(values))


def build_row(
    label: str,
    rvv_dir: Path,
    qbs_dir: Path,
    git_head: str,
) -> dict[str, str | int | float]:
    require_pass(rvv_dir)
    require_pass(qbs_dir)
    rvv = read_one(rvv_dir / "result.csv")
    qbs = read_one(qbs_dir / "result.csv")
    qbs_perf = read_one(qbs_dir / "qbs_perf.csv")
    rvv_metrics = read_phase(rvv_dir / "metrics.csv", "total")
    qbs_metrics = read_phase(qbs_dir / "metrics.csv", "total")
    check_pair(rvv, qbs)
    check_qbs_perf(qbs, qbs_perf)
    check_metrics(rvv, rvv_metrics)
    check_metrics(qbs, qbs_metrics)
    rvv_provenance = read_provenance(rvv_dir / "provenance.json")
    qbs_provenance = read_provenance(qbs_dir / "provenance.json")
    provenance = check_provenance_pair(rvv_provenance, qbs_provenance)

    rvv_compute = number(rvv, "compute_cycles")
    qbs_compute = number(qbs, "compute_cycles")
    rvv_matmul = number(rvv, "matmul_cycles")
    qbs_matmul = number(qbs, "matmul_cycles")
    rvv_bus_bytes = number(rvv_metrics, "axi_r_bus_bytes")
    qbs_bus_bytes = number(qbs_metrics, "axi_r_bus_bytes")
    rvv_retired = number(rvv_metrics, "retired_inst_count")
    qbs_retired = number(qbs_metrics, "retired_inst_count")
    rvv_vec_retired = number(rvv_metrics, "retired_vector_inst_count")
    qbs_vec_retired = number(qbs_metrics, "retired_vector_inst_count")

    row: dict[str, str | int | float] = {
        "workload": label,
        "model": str(provenance["model"]),
        "operator": str(read_provenance(rvv_dir / "provenance.json")["operator"]),
        "phase": str(read_provenance(rvv_dir / "provenance.json")["phase"]),
        "format": str(read_provenance(rvv_dir / "provenance.json")["weight_type"]),
        "k": number(rvv, "k"),
        "n": number(rvv, "rows"),
        "m": number(rvv, "inputs"),
        "git_head": git_head,
        "rvv_case": str(rvv["case"]),
        "qbs_case": str(qbs["case"]),
        "rvv_compute_cycles": rvv_compute,
        "qbs_compute_cycles": qbs_compute,
        "compute_speedup": ratio(rvv_compute, qbs_compute),
        "rvv_matmul_cycles": rvv_matmul,
        "qbs_matmul_cycles": qbs_matmul,
        "matmul_speedup": ratio(rvv_matmul, qbs_matmul),
        "rvv_axi_r_bus_bytes": rvv_bus_bytes,
        "qbs_axi_r_bus_bytes": qbs_bus_bytes,
        "qbs_to_rvv_axi_r_bus_bytes": ratio(qbs_bus_bytes, rvv_bus_bytes),
        "rvv_retired_inst_count": rvv_retired,
        "qbs_retired_inst_count": qbs_retired,
        "qbs_to_rvv_retired_inst_count": ratio(qbs_retired, rvv_retired),
        "rvv_retired_vector_inst_count": rvv_vec_retired,
        "qbs_retired_vector_inst_count": qbs_vec_retired,
        "qbs_to_rvv_retired_vector_inst_count": ratio(
            qbs_vec_retired, rvv_vec_retired
        ),
        "rvv_analytical_input_bytes": number(rvv, "logical_read_bytes"),
        "qbs_analytical_input_bytes": number(qbs, "logical_read_bytes"),
        "rvv_mismatches": number(rvv, "mismatches"),
        "qbs_mismatches": number(qbs, "mismatches"),
        "rvv_max_abs": rvv.get("max_abs", "NA"),
        "qbs_max_abs": qbs.get("max_abs", "NA"),
        "rvv_simv_sha256": file_sha256(rvv_dir / "simv"),
        "qbs_simv_sha256": file_sha256(qbs_dir / "simv"),
        "rvv_elf_sha256": file_sha256(rvv_dir / "benchmark.elf"),
        "qbs_elf_sha256": file_sha256(qbs_dir / "benchmark.elf"),
        "qbs_descriptor_mode": qbs_provenance.get("qbs_descriptor_mode", "legacy"),
        "qbs_command_setup_in_timed_region": qbs_provenance.get(
            "qbs_command_setup_in_timed_region", "unknown"
        ),
        "qbs_runtime_timed_region": qbs_provenance.get(
            "runtime_timed_region", "unknown"
        ),
    }
    for field, value in qbs_perf.items():
        if field != "case":
            row[f"qbs_{field}"] = value
    row.update(provenance)
    return row


def write_markdown(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    setup_modes = {str(row["qbs_command_setup_in_timed_region"]) for row in rows}
    if setup_modes == {"True"}:
        qbs_scope = (
            "QBS includes per-command descriptor construction, command setup, "
            "execution, and result stores in the timed region."
        )
    elif setup_modes == {"False"}:
        qbs_scope = "QBS descriptor construction is excluded from these timings."
    else:
        qbs_scope = (
            "The QBS command-setup timing scope is legacy or mixed; inspect the "
            "per-row provenance fields before interpreting the result."
        )
    lines = [
        "# Real-model operator-slice RVV/QBS closure",
        "",
        f"Source commit: `{rows[0]['git_head']}`.",
        "Both paths use persistent x32 weight repacking and include runtime "
        "F32-to-Q8 activation quantization. Offline weight repacking is excluded "
        "from both timed paths. " + qbs_scope,
        "",
        "| Workload | Format | KxNxM | Compute speedup | Matmul speedup | AXI R bytes RVV | AXI R bytes QBS | QBS/RVV bus bytes | QBS/RVV retired inst. |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {workload} | {format} | {k}x{n}x{m} | {compute:.2f}x | "
            "{matmul:.2f}x | {rvv_bus} | {qbs_bus} | {bus_ratio:.3f} | "
            "{inst_ratio:.3f} |".format(
                **row,
                compute=float(row["compute_speedup"]),
                matmul=float(row["matmul_speedup"]),
                rvv_bus=int(row["rvv_axi_r_bus_bytes"]),
                qbs_bus=int(row["qbs_axi_r_bus_bytes"]),
                bus_ratio=float(row["qbs_to_rvv_axi_r_bus_bytes"]),
                inst_ratio=float(row["qbs_to_rvv_retired_inst_count"]),
            )
        )
    compute_gmean = geometric_mean(
        [float(row["compute_speedup"]) for row in rows]
    )
    matmul_gmean = geometric_mean(
        [float(row["matmul_speedup"]) for row in rows]
    )
    lines += [
        "",
        f"Geometric mean: {compute_gmean:.2f}x compute and "
        f"{matmul_gmean:.2f}x matrix-phase speedup.",
        "`AXI R bytes` is measured phase-gated bus traffic. "
        "`analytical_input_bytes` remains in the CSV only as a formula-based "
        "tensor/descriptor footprint and is not interpreted as traffic.",
        "These are real-model operator slices, not end-to-end model throughput.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rvv-root", type=Path, required=True)
    parser.add_argument("--qbs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--expected-git-head")
    args = parser.parse_args()

    rvv_root = args.rvv_root.resolve()
    qbs_root = args.qbs_root.resolve()
    if read_root_value(rvv_root, "mode") != "rvv":
        raise RuntimeError(f"not an RVV run root: {rvv_root}")
    if read_root_value(qbs_root, "mode") != "qbs":
        raise RuntimeError(f"not a QBS run root: {qbs_root}")
    if read_root_value(rvv_root, "l2_mb") != read_root_value(qbs_root, "l2_mb"):
        raise RuntimeError("RVV/QBS L2 size mismatch")
    git_head = read_root_value(rvv_root, "git_head")
    if git_head != read_root_value(qbs_root, "git_head"):
        raise RuntimeError("RVV/QBS source commit mismatch")
    if args.expected_git_head and git_head != args.expected_git_head:
        raise RuntimeError(
            f"source revision mismatch: expected {args.expected_git_head}, got {git_head}"
        )

    rows = [
        build_row(label, rvv_root / rvv_case, qbs_root / qbs_case, git_head)
        for label, rvv_case, qbs_case in CASES
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output} ({len(rows)} strict RVV/QBS pairs)")
    if args.markdown_output is not None:
        write_markdown(args.markdown_output, rows)
        print(f"wrote {args.markdown_output}")


if __name__ == "__main__":
    main()
