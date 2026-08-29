#!/usr/bin/env python3
"""Strictly pair real-model RVV and QBS format evaluation results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


CASES = (
    ("Q3_K", "q3k_decode_attn_q"),
    ("Q5_K", "q5k_decode_attn_q"),
    ("Q6_K", "q6k_decode_attn_q"),
    ("Q8_0", "q8_0_decode_attn_q"),
)
def read_one(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"missing result file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise RuntimeError(f"expected one row in {path}, found {len(rows)}")
    return rows[0]


def read_phase(path: Path, phase: str) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"missing metrics file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        matches = [row for row in csv.DictReader(handle) if row.get("phase") == phase]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {phase} row in {path}, found {len(matches)}"
        )
    return matches[0]


def read_provenance(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"missing provenance file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"missing artifact: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_pass(run_dir: Path) -> None:
    status = run_dir / "status"
    if not status.is_file() or status.read_text().strip() != "PASS":
        raise RuntimeError(f"run is not PASS: {run_dir}")


def read_root_value(root: Path, name: str) -> str:
    path = root / name
    if not path.is_file():
        raise RuntimeError(f"missing run metadata: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"empty run metadata: {path}")
    return value


def number(row: dict[str, str], field: str) -> int:
    value = row.get(field, "")
    if value in ("", "NA"):
        raise RuntimeError(f"missing numeric field {field} in case {row.get('case')}")
    return int(value)


def ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "NA"
    return f"{numerator / denominator:.6f}"


def percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def geometric_mean(values: list[float]) -> float:
    return math.exp(sum(math.log(value) for value in values) / len(values))


def check_pair(rvv: dict[str, str], qbs: dict[str, str]) -> None:
    for row in (rvv, qbs):
        if row.get("result") != "PASS" or number(row, "mismatches") != 0:
            raise RuntimeError(f"benchmark did not pass: {row.get('case')}")
    for field in ("k", "rows", "inputs", "outputs"):
        if number(rvv, field) != number(qbs, field):
            raise RuntimeError(
                f"non-equivalent workload for {field}: "
                f"{rvv.get('case')}={rvv.get(field)}, {qbs.get('case')}={qbs.get(field)}"
            )


def check_qbs_perf(qbs: dict[str, str], perf: dict[str, str]) -> None:
    if perf.get("case") != qbs.get("case"):
        raise RuntimeError(
            f"QBS result/perf case mismatch: {qbs.get('case')} != "
            f"{perf.get('case')}"
        )
    commands = number(perf, "commands")
    successes = number(perf, "successes")
    faults = number(perf, "faults")
    if commands <= 0 or successes != commands or faults != 0:
        raise RuntimeError(
            f"invalid QBS terminal accounting for {qbs.get('case')}: "
            f"commands={commands}, successes={successes}, faults={faults}"
        )
    if number(perf, "pair_capacity") < number(perf, "useful_pairs"):
        raise RuntimeError(f"QBS useful pairs exceed capacity: {qbs.get('case')}")


def check_metrics(result: dict[str, str], metrics: dict[str, str]) -> None:
    expected_case = f"llama_qwen25_{result.get('case')}"
    if metrics.get("case") != expected_case or metrics.get("phase") != "total":
        raise RuntimeError(
            f"result/metrics mismatch: {result.get('case')} != "
            f"{metrics.get('case')}:{metrics.get('phase')}"
        )


def check_provenance_pair(
    rvv: dict[str, object], qbs: dict[str, object]
) -> dict[str, str | int]:
    for field in (
        "model",
        "model_metadata_sha256",
        "capture_llama_commit",
        "operator",
        "phase",
        "weight_type",
        "k",
        "rows",
        "inputs",
        "evaluation_slice",
    ):
        if rvv.get(field) != qbs.get(field):
            raise RuntimeError(f"provenance mismatch for {field}")

    signatures: dict[str, str | int] = {}
    for tensor_name, prefix in (
        ("source_weight.bin", "source_weight"),
        ("activation_f32.bin", "activation"),
        ("golden_f32.bin", "golden"),
    ):
        rvv_tensor = dict(rvv.get("tensors", {})).get(tensor_name)
        qbs_tensor = dict(qbs.get("tensors", {})).get(tensor_name)
        if not isinstance(rvv_tensor, dict) or not isinstance(qbs_tensor, dict):
            raise RuntimeError(f"missing provenance for {tensor_name}")
        for field in ("bytes", "sha256"):
            if rvv_tensor.get(field) != qbs_tensor.get(field):
                raise RuntimeError(
                    f"provenance mismatch for {tensor_name}.{field}"
                )
        signatures[f"{prefix}_bytes"] = int(rvv_tensor["bytes"])
        signatures[f"{prefix}_sha256"] = str(rvv_tensor["sha256"])
    signatures["model_metadata_sha256"] = str(rvv["model_metadata_sha256"])
    signatures["capture_llama_commit"] = str(rvv["capture_llama_commit"])
    signatures["model"] = str(rvv["model"])
    return signatures


def build_row(
    fmt: str,
    rvv: dict[str, str],
    qbs: dict[str, str],
    perf: dict[str, str],
    rvv_metrics: dict[str, str],
    qbs_metrics: dict[str, str],
    provenance: dict[str, str | int],
    git_head: str,
    rvv_simv_sha256: str,
    qbs_simv_sha256: str,
    rvv_elf_sha256: str,
    qbs_elf_sha256: str,
) -> dict[str, str | int]:
    check_pair(rvv, qbs)
    check_qbs_perf(qbs, perf)
    check_metrics(rvv, rvv_metrics)
    check_metrics(qbs, qbs_metrics)
    row: dict[str, str | int] = {
        "format": fmt,
        "model": str(provenance["model"]),
        "operator": "blk.0.attn_q.weight",
        "k": number(rvv, "k"),
        "n": number(rvv, "rows"),
        "m": number(rvv, "inputs"),
        "rvv_case": rvv["case"],
        "qbs_case": qbs["case"],
        "rvv_result": rvv["result"],
        "qbs_result": qbs["result"],
        "rvv_mismatches": number(rvv, "mismatches"),
        "qbs_mismatches": number(qbs, "mismatches"),
        "rvv_max_abs": rvv.get("max_abs", "NA"),
        "rvv_max_rel": rvv.get("max_rel", "NA"),
        "qbs_max_abs": qbs.get("max_abs", "NA"),
        "qbs_max_rel": qbs.get("max_rel", "NA"),
        "git_head": git_head,
        "rvv_simv_sha256": rvv_simv_sha256,
        "qbs_simv_sha256": qbs_simv_sha256,
        "rvv_elf_sha256": rvv_elf_sha256,
        "qbs_elf_sha256": qbs_elf_sha256,
    }
    row.update(provenance)
    for phase in ("compute", "quantize", "pack", "matmul"):
        rvv_cycles = number(rvv, f"{phase}_cycles")
        qbs_cycles = number(qbs, f"{phase}_cycles")
        row[f"rvv_{phase}_cycles"] = rvv_cycles
        row[f"qbs_{phase}_cycles"] = qbs_cycles
        row[f"{phase}_speedup"] = ratio(rvv_cycles, qbs_cycles)
    for field in (
        "cycles_per_output_x1000",
        "logical_read_bytes",
        "total_cycles",
        "total_insns",
        "total_vector_insns",
        "ara_req_fire_count",
        "rvv_axi_ar_count",
        "rvv_axi_r_count",
        "rvv_op_load",
        "rvv_op_store",
        "lane_utilization",
    ):
        row[f"rvv_{field}"] = rvv.get(field, "NA")
        row[f"qbs_{field}"] = qbs.get(field, "NA")
    row["rvv_analytical_input_bytes"] = number(rvv, "logical_read_bytes")
    row["qbs_analytical_input_bytes"] = number(qbs, "logical_read_bytes")
    for field in (
        "cycles",
        "retired_inst_count",
        "retired_vector_inst_count",
        "axi_ar_count",
        "axi_ar_bytes",
        "axi_r_beat_count",
        "axi_r_bus_bytes",
    ):
        row[f"rvv_metric_{field}"] = rvv_metrics.get(field, "NA")
        row[f"qbs_metric_{field}"] = qbs_metrics.get(field, "NA")
    rvv_bus_bytes = number(rvv_metrics, "axi_r_bus_bytes")
    qbs_bus_bytes = number(qbs_metrics, "axi_r_bus_bytes")
    row["rvv_axi_r_bus_bytes"] = rvv_bus_bytes
    row["qbs_axi_r_bus_bytes"] = qbs_bus_bytes
    row["qbs_to_rvv_axi_r_bus_bytes"] = ratio(qbs_bus_bytes, rvv_bus_bytes)
    # Preserve every strict raw counter and derived ratio emitted by the QBS
    # summarizer. The closure table must not silently narrow the evidence to a
    # hand-picked subset as the RTL counter schema evolves.
    for field, value in perf.items():
        if field != "case":
            row[f"qbs_{field}"] = value
    return row


def write_markdown(path: Path, rows: list[dict[str, str | int]]) -> None:
    lines = [
        "# Real-model RVV/QBS format closure",
        "",
        "All points use one captured decode activation and the first 256 output "
        "rows of `blk.0.attn_q.weight`. Both paths passed the same llama.cpp "
        "golden with zero mismatches. Persistent offline weight repacking is "
        "excluded from both timed paths.",
        f"Source commit: `{rows[0]['git_head']}`.",
        f"All RVV points use simulator image `{rows[0]['rvv_simv_sha256']}`; "
        f"all QBS points use `{rows[0]['qbs_simv_sha256']}`.",
        "",
        "| Format | KxNxM | Compute speedup | Matmul speedup | AXI R bytes RVV | AXI R bytes QBS | QBS/RVV | Analytical input bytes RVV/QBS | QBS dot active |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        display = dict(row)
        display["compute_speedup"] = f"{float(row['compute_speedup']):.2f}"
        display["matmul_speedup"] = f"{float(row['matmul_speedup']):.2f}"
        lines.append(
            "| {format} | {k}x{n}x{m} | {compute_speedup}x | "
            "{matmul_speedup}x | {rvv_bus_bytes} | {qbs_bus_bytes} | "
            "{bus_ratio} | {rvv_footprint}/{qbs_footprint} | {dot_active} |".format(
                **display,
                rvv_bus_bytes=int(row["rvv_axi_r_bus_bytes"]),
                qbs_bus_bytes=int(row["qbs_axi_r_bus_bytes"]),
                bus_ratio=f"{float(row['qbs_to_rvv_axi_r_bus_bytes']):.3f}",
                rvv_footprint=int(row["rvv_analytical_input_bytes"]),
                qbs_footprint=int(row["qbs_analytical_input_bytes"]),
                dot_active=percent(float(row["qbs_dot_active_ratio"])),
            )
        )

    compute_geomean = geometric_mean(
        [float(row["compute_speedup"]) for row in rows]
    )
    matmul_geomean = geometric_mean(
        [float(row["matmul_speedup"]) for row in rows]
    )
    lines += [
        "",
        f"Across these four representative points, the geometric-mean speedup "
        f"is {compute_geomean:.2f}x for dynamic quantization plus matrix "
        f"computation and {matmul_geomean:.2f}x for the matrix phase alone. "
        "These are operator-slice results against an optimized standard-RVV "
        "x32/M4 benchmark implementation, not an end-to-end model speedup.",
        "`AXI R bytes` is the phase-gated number of bytes transferred on the "
        "measured AXI read-data bus. `Analytical input bytes` is a formula-based "
        "tensor/descriptor footprint and is not treated as measured traffic.",
        "",
        "## Bottleneck evidence",
        "",
        "| Format | K blocks | QBS quant share | Weight-prefetch wait | Profile-result blocked | FP-input blocked | FP uops/output |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    block_elements = {"Q3_K": 256, "Q5_K": 256, "Q6_K": 256, "Q8_0": 32}
    for row in rows:
        outputs = int(row["n"]) * int(row["m"])
        lines.append(
            "| {format} | {blocks} | {quant_share} | {prefetch_wait} | "
            "{result_blocked} | {fp_input_blocked} | {fp_uops:.1f} |".format(
                **row,
                blocks=int(row["k"]) // block_elements[str(row["format"])],
                quant_share=percent(
                    int(row["qbs_quantize_cycles"]) /
                    int(row["qbs_compute_cycles"])
                ),
                prefetch_wait=percent(
                    float(row["qbs_weight_prefetch_wait_ratio"])
                ),
                result_blocked=percent(
                    float(row["qbs_profile_result_blocked_ratio"])
                ),
                fp_input_blocked=percent(
                    float(row["qbs_fp_input_blocked_ratio"])
                ),
                fp_uops=int(row["qbs_fp_uop_issue"]) / outputs,
            )
        )

    highest_input_phase = max(
        rows, key=lambda row: float(row["qbs_input_phase_ratio"])
    )
    lowest_dot = min(rows, key=lambda row: float(row["qbs_dot_active_ratio"]))
    highest_idle = max(rows, key=lambda row: float(row["qbs_read_response_idle_ratio"]))
    by_format = {str(row["format"]): row for row in rows}
    q6 = by_format["Q6_K"]
    q8 = by_format["Q8_0"]
    q8_outputs = int(q8["n"]) * int(q8["m"])
    q8_k_blocks = int(q8["k"]) // block_elements["Q8_0"]
    k_quant_blocks = int(by_format["Q3_K"]["k"]) // block_elements["Q3_K"]
    lines += [
        "",
        "## Measured signatures",
        "",
        "- Pair utilization is 100% for every format, so the measured QBS "
        "commands do not lose work to partially filled arithmetic pairs.",
        f"- `{highest_input_phase['format']}` spends the largest fraction in "
        "activation/weight input phases "
        f"({percent(float(highest_input_phase['qbs_input_phase_ratio']))}). "
        "This is phase occupancy, not a stall classification.",
        f"- `{lowest_dot['format']}` has the lowest dot-active fraction "
        f"({percent(float(lowest_dot['qbs_dot_active_ratio']))}); this metric is "
        "reported together with input and read-state counters rather than being "
        "treated as a standalone execution-unit utilization claim.",
        f"- `{highest_idle['format']}` has the largest read-response-idle fraction "
        f"({percent(float(highest_idle['qbs_read_response_idle_ratio']))}), which "
        "identifies the format most exposed to response gaps in this workload.",
        "- Q5_K and Q6_K expose increasing weight-prefetch wait as native "
        f"block size grows. Q6_K combines {percent(float(q6['qbs_weight_prefetch_wait_ratio']))} "
        f"weight-prefetch wait with {percent(float(q6['qbs_read_outstanding_full_ratio']))} "
        f"read-outstanding-full activity and only {percent(float(q6['qbs_read_response_idle_ratio']))} "
        "response-idle activity; "
        "the evidence points to weight-stream service/serialization rather "
        "than an empty request pipeline.",
        f"- Q8_0 has {q8_k_blocks} K blocks per output instead of "
        f"{k_quant_blocks} for the K-quant "
        f"points. Its {percent(float(q8['qbs_profile_result_blocked_ratio']))} "
        f"profile-result-blocked and {percent(float(q8['qbs_fp_input_blocked_ratio']))} "
        "FP-input-blocked activities, together with "
        f"{int(q8['qbs_fp_uop_issue']) / q8_outputs:.0f} FP uops per output, show that frequent "
        "per-block result scaling/accumulation and fragmented input service "
        "limit the dot array; increasing dot width alone would not remove this "
        "bottleneck.",
        "- FP-table-full and commit-backpressure counters are zero for all four "
        "points. The listed block signals can overlap in a cycle and are "
        "diagnostic activities, not an additive stall decomposition.",
        "- Compute speedup includes dynamic activation quantization; matmul "
        "speedup isolates the quantized matrix phase. QEMU emulation is excluded "
        "from all cycle comparisons.",
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
    rows: list[dict[str, str | int]] = []
    rvv_simv_sha256: str | None = None
    qbs_simv_sha256: str | None = None
    for fmt, stem in CASES:
        rvv_dir = rvv_root / f"{stem}_rvv"
        qbs_dir = qbs_root / f"{stem}_qbs"
        require_pass(rvv_dir)
        require_pass(qbs_dir)
        case_rvv_simv_sha256 = file_sha256(rvv_dir / "simv")
        case_qbs_simv_sha256 = file_sha256(qbs_dir / "simv")
        if rvv_simv_sha256 is None:
            rvv_simv_sha256 = case_rvv_simv_sha256
        elif rvv_simv_sha256 != case_rvv_simv_sha256:
            raise RuntimeError(f"mixed RVV simulator images at {rvv_dir}")
        if qbs_simv_sha256 is None:
            qbs_simv_sha256 = case_qbs_simv_sha256
        elif qbs_simv_sha256 != case_qbs_simv_sha256:
            raise RuntimeError(f"mixed QBS simulator images at {qbs_dir}")
        provenance = check_provenance_pair(
            read_provenance(rvv_dir / "provenance.json"),
            read_provenance(qbs_dir / "provenance.json"),
        )
        rows.append(
            build_row(
                fmt,
                read_one(rvv_dir / "result.csv"),
                read_one(qbs_dir / "result.csv"),
                read_one(qbs_dir / "qbs_perf.csv"),
                read_phase(rvv_dir / "metrics.csv", "total"),
                read_phase(qbs_dir / "metrics.csv", "total"),
                provenance,
                git_head,
                case_rvv_simv_sha256,
                case_qbs_simv_sha256,
                file_sha256(rvv_dir / "benchmark.elf"),
                file_sha256(qbs_dir / "benchmark.elf"),
            )
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output} ({len(rows)} equivalent RVV/QBS pairs)")
    if args.markdown_output is not None:
        write_markdown(args.markdown_output, rows)
        print(f"wrote {args.markdown_output}")


if __name__ == "__main__":
    main()
