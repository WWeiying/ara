#!/usr/bin/env python3
"""Validate and summarize the controlled QBS cross-operator RTL ablation."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


BENCH_RE = re.compile(r"\bQBS_REAL_BENCH\s+(.*)$")
ACCESS_FILL = 1
ACCESS_REUSE = 2
ACCESS_RELEASE = 3


def one_csv_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise RuntimeError(f"{path}: expected one data row, found {len(rows)}")
    return rows[0]


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def bench_record(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = BENCH_RE.search(line)
        if match is None:
            continue
        result = dict(
            item.split("=", 1)
            for item in match.group(1).split()
            if "=" in item
        )
    if not result:
        raise RuntimeError(f"{path}: no QBS_REAL_BENCH record")
    return result


def integer(row: dict[str, str], key: str) -> int:
    return int(row[key], 0)


def expected_accesses(operations: int, tiles: int, cross_op: bool) -> list[int]:
    if operations < 2 or tiles < 2:
        raise RuntimeError(
            "controlled cross-operator ablation requires at least two operations and tiles"
        )
    commands = operations * tiles
    if cross_op:
        return [ACCESS_FILL] + [ACCESS_REUSE] * (commands - 2) + [ACCESS_RELEASE]
    sequence: list[int] = []
    for _ in range(operations):
        sequence.extend(
            [ACCESS_FILL] + [ACCESS_REUSE] * (tiles - 2) + [ACCESS_RELEASE]
        )
    return sequence


def validate_run(run_dir: Path, cross_op: bool) -> tuple[
    dict[str, str], dict[str, str], list[dict[str, str]]
]:
    if (run_dir / "status").read_text(encoding="utf-8").strip() != "PASS":
        raise RuntimeError(f"{run_dir}: run status is not PASS")
    bench = bench_record(run_dir / "run.vcs.log")
    perf = one_csv_row(run_dir / "qbs_perf.csv")
    commands = csv_rows(run_dir / "qbs_commands.csv")
    operations = integer(bench, "operations")
    tiles = integer(bench, "tiles")
    if bench["result"] != "PASS" or integer(bench, "mismatches") != 0:
        raise RuntimeError(f"{run_dir}: benchmark result is not exact PASS")
    if bool(integer(bench, "cross_op_reuse")) != cross_op:
        raise RuntimeError(f"{run_dir}: cross-op mode does not match the run role")
    if len(commands) != operations * tiles:
        raise RuntimeError(f"{run_dir}: command count does not match operation chain")
    actual_accesses = [integer(row, "activation_access") for row in commands]
    expected = expected_accesses(operations, tiles, cross_op)
    if actual_accesses != expected:
        raise RuntimeError(
            f"{run_dir}: activation access sequence {actual_accesses} != {expected}"
        )
    for index, command in enumerate(commands, 1):
        if integer(command, "success") != 1 or integer(command, "fault") != 0:
            raise RuntimeError(f"{run_dir}: command {index} did not succeed")
        if integer(command, "validation_fault") != 0:
            raise RuntimeError(f"{run_dir}: command {index} had a validation fault")
    return bench, perf, commands


def write_csv(path: Path, summary: dict[str, object]) -> None:
    scalar = {
        key: value for key, value in summary.items()
        if not isinstance(value, (dict, list))
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scalar))
        writer.writeheader()
        writer.writerow(scalar)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation-run", type=Path, required=True)
    parser.add_argument("--cross-op-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    baseline, baseline_perf, baseline_commands = validate_run(
        args.operation_run.resolve(), False
    )
    optimized, optimized_perf, optimized_commands = validate_run(
        args.cross_op_run.resolve(), True
    )

    equal_work_fields = (
        "operations", "outputs_per_operation", "result_count", "k", "rows",
        "inputs", "tiles", "checksum",
    )
    unequal = [field for field in equal_work_fields
               if baseline[field] != optimized[field]]
    perf_equal_fields = (
        "commands", "successes", "faults", "tiles", "weight_bytes",
        "activation_bytes", "useful_pairs", "pair_capacity",
        "accumulator_updates", "commit_groups",
    )
    unequal += [f"qbs_perf.{field}" for field in perf_equal_fields
                if baseline_perf[field] != optimized_perf[field]]
    if unequal:
        raise RuntimeError("ablation changed semantic work: " + ", ".join(unequal))

    baseline_cycles = integer(baseline, "timed_cycles")
    optimized_cycles = integer(optimized, "timed_cycles")
    quantization_bytes_saved = (
        (integer(baseline, "quantizations") - integer(optimized, "quantizations"))
        * integer(baseline, "inputs") * integer(baseline, "k") * 4
    )
    activation_axi_bytes_saved = (
        integer(optimized_perf, "activation_axi_bytes_saved")
        - integer(baseline_perf, "activation_axi_bytes_saved")
    )
    qbs_payload_bytes_saved = (
        integer(baseline_perf, "payload_bytes")
        - integer(optimized_perf, "payload_bytes")
    )
    logical_read_bytes_saved = (
        integer(baseline, "logical_read_bytes")
        - integer(optimized, "logical_read_bytes")
    )
    expected_logical_saving = quantization_bytes_saved + activation_axi_bytes_saved
    if activation_axi_bytes_saved != qbs_payload_bytes_saved:
        raise RuntimeError("QBS payload delta does not equal activation AXI saving")
    if logical_read_bytes_saved != expected_logical_saving:
        raise RuntimeError("logical read delta does not match strict byte accounting")

    summary: dict[str, object] = {
        "status": "PASS",
        "case": "Qwen2.5_blk0_attn_q_Q4_K_K1536_N64_M1_chain3",
        "operations": integer(baseline, "operations"),
        "commands": len(baseline_commands),
        "result_count": integer(baseline, "result_count"),
        "checksum": baseline["checksum"],
        "baseline_quantizations": integer(baseline, "quantizations"),
        "cross_op_quantizations": integer(optimized, "quantizations"),
        "quantizations_eliminated": (
            integer(baseline, "quantizations")
            - integer(optimized, "quantizations")
        ),
        "baseline_cycles": baseline_cycles,
        "cross_op_cycles": optimized_cycles,
        "cycles_saved": baseline_cycles - optimized_cycles,
        "speedup": baseline_cycles / optimized_cycles,
        "cycle_reduction": (baseline_cycles - optimized_cycles) / baseline_cycles,
        "baseline_quantize_cycles": integer(baseline, "quantize_cycles"),
        "cross_op_quantize_cycles": integer(optimized, "quantize_cycles"),
        "quantize_cycles_saved": (
            integer(baseline, "quantize_cycles")
            - integer(optimized, "quantize_cycles")
        ),
        "baseline_matmul_cycles": integer(baseline, "matmul_cycles"),
        "cross_op_matmul_cycles": integer(optimized, "matmul_cycles"),
        "matmul_cycles_saved": (
            integer(baseline, "matmul_cycles")
            - integer(optimized, "matmul_cycles")
        ),
        "quantization_input_bytes_saved": quantization_bytes_saved,
        "activation_axi_bytes_saved": activation_axi_bytes_saved,
        "logical_read_bytes_saved": logical_read_bytes_saved,
        "operation_access_sequence": [
            integer(row, "activation_access") for row in baseline_commands
        ],
        "cross_op_access_sequence": [
            integer(row, "activation_access") for row in optimized_commands
        ],
        "operation_run": str(args.operation_run.resolve()),
        "cross_op_run": str(args.cross_op_run.resolve()),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_csv(args.output_dir / "summary.csv", summary)
    (args.output_dir / "summary.md").write_text(
        "\n".join([
            "# QBS Cross-Operator RTL Ablation",
            "",
            "| Metric | Operation scope | Cross-operator scope |",
            "|---|---:|---:|",
            f"| Quantizations | {summary['baseline_quantizations']} | "
            f"{summary['cross_op_quantizations']} |",
            f"| Timed cycles | {baseline_cycles} | {optimized_cycles} |",
            f"| Quantize cycles | {summary['baseline_quantize_cycles']} | "
            f"{summary['cross_op_quantize_cycles']} |",
            f"| Matmul cycles | {summary['baseline_matmul_cycles']} | "
            f"{summary['cross_op_matmul_cycles']} |",
            "",
            f"Speedup: `{summary['speedup']:.6f}x`; cycle reduction: "
            f"`{100 * summary['cycle_reduction']:.3f}%`.",
            "",
            f"Strict traffic saving: `{logical_read_bytes_saved} B` = "
            f"`{quantization_bytes_saved} B` F32 quantization input + "
            f"`{activation_axi_bytes_saved} B` Q8_K activation AXI traffic.",
            "",
            "All 192 outputs and the full checksum are equal. This is a "
            "controlled three-operation replay of one real Qwen2.5 Q4_K "
            "weight slice and activation, not a claim that the replayed "
            "weights are three distinct Q/K/V tensors.",
            "",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
