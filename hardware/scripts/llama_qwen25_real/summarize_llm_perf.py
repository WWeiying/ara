#!/usr/bin/env python3
"""Convert phase-tagged LLM RTL counters into a phase-per-row CSV file."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


PREFIX = "[LLM_PERF] "
PHASE_ORDER = {"total": 0, "quantize": 1, "pack": 2, "matmul": 3}


def parse_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.startswith(PREFIX) or " phase=" not in line:
            continue
        row: dict[str, str] = {}
        for item in line[len(PREFIX) :].split():
            if "=" in item:
                key, value = item.split("=", 1)
                row[key] = value
        if row.get("phase") in PHASE_ORDER:
            rows.append(row)
    if not rows:
        raise RuntimeError("metrics log contains no phase-tagged [LLM_PERF] rows")

    # Appended simulation logs may contain earlier runs.  Keep the final set.
    last_case = rows[-1].get("case")
    selected: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("case") == last_case:
            selected[row["phase"]] = row
    return sorted(selected.values(), key=lambda row: PHASE_ORDER[row["phase"]])


def ratio(numerator: str, denominator: str) -> str:
    den = int(denominator)
    return "NA" if den == 0 else f"{int(numerator) / den:.9g}"


def add_derived(row: dict[str, str]) -> None:
    cycles = row["cycles"]
    row["req_per_cycle"] = ratio(row["req_fire_count"], cycles)
    row["elements_per_cycle"] = ratio(row["vector_element_count"], cycles)
    row["lane_active_ratio"] = ratio(row["lane_active_cycles"], cycles)
    row["req_blocked_ratio"] = ratio(row["req_blocked_cycles"], cycles)
    row["avg_queue_occ"] = ratio(row["queue_occ_sum"], cycles)
    row["avg_inflight"] = ratio(row["inflight_occ_sum"], cycles)
    row["avg_read_outstanding"] = ratio(row["read_outstanding_occ_sum"], cycles)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = parse_rows(args.metrics_log.read_text(errors="replace"))
    for row in rows:
        add_derived(row)

    preferred = [
        "case", "phase", "cycles", "backend_busy_cycles", "lane_active_cycles",
        "lane_active_ratio", "req_valid_cycles", "req_fire_count", "req_per_cycle",
        "req_blocked_cycles", "req_blocked_ratio", "vector_element_count",
        "elements_per_cycle", "retired_inst_count", "retired_vector_inst_count",
        "retired_scalar_inst_count", "load_count", "load_unit_count", "load_strided_count",
        "load_indexed_count", "store_count", "store_unit_count", "store_strided_count",
        "store_indexed_count", "bitwise_count", "shift_count", "int_alu_count", "int_mul_count",
        "int_widen_mul_count", "int_mac_count", "int_widen_mac_count",
        "int_reduction_count", "fp_reduction_count", "narrow_count",
        "fp_arith_count", "permute_count", "mask_count", "scalar_move_count",
        "other_count", "unit_load_span_bytes", "unit_store_span_bytes",
        "masked_mem_count", "axi_ar_count", "axi_ar_bytes", "axi_r_beat_count",
        "axi_r_bus_bytes", "axi_aw_count", "axi_aw_bytes", "axi_w_beat_count",
        "axi_w_useful_bytes", "axi_b_count", "axi_ar_stall_cycles",
        "axi_r_stall_cycles", "axi_aw_stall_cycles", "axi_w_stall_cycles",
        "avg_read_outstanding", "read_outstanding_max", "avg_queue_occ",
        "queue_occ_max", "queue_full_cycles", "avg_inflight", "inflight_occ_max",
        "queue_resource_block_cycles", "no_vid_block_cycles",
        "lane_desync_block_cycles", "operand_block_cycles", "mask_block_cycles",
        "slide_block_cycles", "hazard_block_cycles", "scalar_result_wait_cycles",
        "lane_alu_operand_fires", "lane_mfpu_operand_fires",
    ]
    fields = preferred + sorted(set().union(*(row.keys() for row in rows)) - set(preferred))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
