#!/usr/bin/env python3
"""Validate and aggregate command-level QBS performance records."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


PREFIX = "[QBS_PERF] "
PAIR_RE = re.compile(r"([a-z0-9_]+)=([0-9]+)")
IDENTITY_FIELDS = {
    "seq",
    "id",
    "m",
    "vlen",
    "lanes",
    "success",
    "fault",
    "validation_fault",
    "validation_error",
    "read_fault",
}
MAX_FIELDS = {"fp_table_occ_max", "read_outstanding_max"}
PHASE_FIELDS = (
    "phase_setup_cycles",
    "phase_activation_cycles",
    "phase_weight_cycles",
    "phase_compute_cycles",
    "phase_overlap_cycles",
    "phase_drain_cycles",
    "phase_scheduler_cycles",
    "phase_commit_cycles",
    "phase_fault_cycles",
    "phase_terminal_cycles",
)
FULL_FIELDS = set(PHASE_FIELDS) | {
    "read_outstanding_occ_sum",
    "read_outstanding_max",
    "read_outstanding_full_cycles",
    "weight_prefetch_wait_cycles",
}
PROBE_FIELDS = {
    "probe_context_start_blocked_cycles",
    "probe_compute_without_dot_issue_cycles",
    "probe_profile_result_blocked_cycles",
    "probe_fp_slot_blocked_cycles",
    "probe_fp_accumulator_blocked_cycles",
    "probe_fp_other_blocked_cycles",
    "probe_fp_input_blocked_cycles",
    "probe_fp_no_schedulable_uop_cycles",
    "probe_fp_busy_cycles",
    "probe_profile_context_occ_sum",
    "probe_profile_two_context_cycles",
    "probe_profile_drain_only_cycles",
    "probe_profile_correction_pending_cycles",
    "probe_profile_result_pending_cycles",
    "probe_read_range_blocked_cycles",
    "probe_read_range_fifo_blocked_cycles",
    "probe_read_ar_slot_blocked_cycles",
    "probe_read_ar_ready_blocked_cycles",
    "probe_read_response_idle_cycles",
    "probe_read_data_sink_blocked_cycles",
    "probe_read_completion_blocked_cycles",
    "probe_read_translation_wait_cycles",
    "probe_weight_wait_no_outstanding_cycles",
    "probe_weight_wait_response_idle_cycles",
    "probe_weight_wait_r_transfer_cycles",
    "probe_weight_wait_r_blocked_cycles",
}


def parse_log(path: Path) -> list[dict[str, int]]:
    records: list[dict[str, int]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        position = line.find(PREFIX)
        if position < 0:
            continue
        fields = {key: int(value) for key, value in PAIR_RE.findall(line[position:])}
        if not fields:
            raise SystemExit(f"{path}:{line_number}: malformed QBS_PERF record")
        records.append(fields)
    if not records:
        raise SystemExit(f"{path}: no QBS_PERF records")
    return records


def validate(records: list[dict[str, int]]) -> list[str]:
    keys = set(records[0])
    errors: list[str] = []
    full_fields_present = FULL_FIELDS & keys
    if full_fields_present and full_fields_present != FULL_FIELDS:
        missing = ", ".join(sorted(FULL_FIELDS - keys))
        errors.append(f"incomplete QBS-Full counter schema; missing: {missing}")
    has_full_counters = FULL_FIELDS <= keys
    probe_fields_present = PROBE_FIELDS & keys
    if probe_fields_present and probe_fields_present != PROBE_FIELDS:
        missing = ", ".join(sorted(PROBE_FIELDS - keys))
        errors.append(f"incomplete QBS probe schema; missing: {missing}")
    has_probe_counters = PROBE_FIELDS <= keys
    for index, record in enumerate(records, 1):
        if set(record) != keys:
            errors.append(f"command {index}: inconsistent field set")
            continue
        if record["seq"] != index:
            errors.append(
                f"command {index}: sequence is {record['seq']}, expected {index}"
            )
        if record["success"] + record["fault"] != 1:
            errors.append(f"command {index}: terminal outcome is not one-hot")
        if record["useful_pairs"] > record["pair_capacity"]:
            errors.append(f"command {index}: useful pairs exceed capacity")
        if record["success"]:
            expected_groups = (
                record["m"] * record["vlen"] // (record["lanes"] * 64)
            )
            if record["commit_groups"] != expected_groups:
                errors.append(
                    f"command {index}: commit_groups={record['commit_groups']}, "
                    f"expected {expected_groups}"
                )
            activation_bytes_saved = record.get("activation_axi_bytes_saved", 0)
            if activation_bytes_saved > record["activation_bytes"]:
                errors.append(
                    f"command {index}: saved activation bytes exceed logical bytes"
                )
            if record["payload_bytes"] != (
                16
                + record["weight_bytes"]
                + record["activation_bytes"]
                - activation_bytes_saved
            ):
                errors.append(
                    f"command {index}: successful payload byte accounting mismatch"
                )
        elif any(
            record[field]
            for field in (
                "tiles",
                "weight_bytes",
                "activation_bytes",
                "useful_pairs",
                "pair_capacity",
                "dot_active_cycles",
                "fp_uop_issue",
                "accumulator_updates",
                "commit_groups",
            )
        ):
            errors.append(f"command {index}: fault retained compute/commit counters")
        if has_full_counters:
            phase_total = sum(record[field] for field in PHASE_FIELDS)
            if phase_total != record["busy_cycles"]:
                errors.append(
                    f"command {index}: exclusive phases total {phase_total}, "
                    f"busy_cycles={record['busy_cycles']}"
                )
            if record["read_outstanding_max"] > 2:
                errors.append(f"command {index}: read outstanding depth exceeded two")
            if record["read_outstanding_occ_sum"] > 2 * record["busy_cycles"]:
                errors.append(
                    f"command {index}: read outstanding occupancy sum is impossible"
                )
            if record["read_outstanding_full_cycles"] > record["busy_cycles"]:
                errors.append(
                    f"command {index}: read outstanding full cycles exceed busy time"
                )
            if (
                record["weight_prefetch_wait_cycles"]
                > record["phase_weight_cycles"]
            ):
                errors.append(
                    f"command {index}: weight-prefetch wait escaped weight phase"
                )
            compute_cycles = (
                record["phase_compute_cycles"] + record["phase_overlap_cycles"]
            )
            if record["dot_active_cycles"] > compute_cycles:
                errors.append(
                    f"command {index}: dot-active cycles exceed compute-state cycles"
                )
        if has_probe_counters:
            classified_fp_block = sum(
                record[field]
                for field in (
                    "probe_fp_slot_blocked_cycles",
                    "probe_fp_accumulator_blocked_cycles",
                    "probe_fp_other_blocked_cycles",
                )
            )
            if classified_fp_block != record["probe_profile_result_blocked_cycles"]:
                errors.append(
                    f"command {index}: FP request blocker classification mismatch"
                )
            if (
                record["probe_compute_without_dot_issue_cycles"]
                > record["phase_compute_cycles"] + record["phase_overlap_cycles"]
            ):
                errors.append(
                    f"command {index}: non-dot compute cycles exceed compute state"
                )
            if record["probe_profile_context_occ_sum"] > 2 * record["busy_cycles"]:
                errors.append(
                    f"command {index}: profile context occupancy is impossible"
                )
            classified_weight_wait = sum(
                record[field]
                for field in (
                    "probe_weight_wait_no_outstanding_cycles",
                    "probe_weight_wait_response_idle_cycles",
                    "probe_weight_wait_r_transfer_cycles",
                    "probe_weight_wait_r_blocked_cycles",
                )
            )
            if classified_weight_wait != record["weight_prefetch_wait_cycles"]:
                errors.append(
                    f"command {index}: weight-wait classification mismatch"
                )
    return errors


def ratio(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.9f}" if denominator else "NA"


def aggregate(case: str, records: list[dict[str, int]]) -> dict[str, str | int]:
    result: dict[str, str | int] = {
        "case": case,
        "commands": len(records),
        "successes": sum(record["success"] for record in records),
        "faults": sum(record["fault"] for record in records),
    }
    for field in records[0]:
        if field in IDENTITY_FIELDS:
            continue
        if field in MAX_FIELDS:
            result[field] = max(record[field] for record in records)
        else:
            result[field] = sum(record[field] for record in records)
    result["pair_utilization"] = ratio(
        int(result["useful_pairs"]), int(result["pair_capacity"])
    )
    result["dot_active_ratio"] = ratio(
        int(result["dot_active_cycles"]), int(result["busy_cycles"])
    )
    result["read_bytes_per_busy_cycle"] = ratio(
        int(result["payload_bytes"]), int(result["busy_cycles"])
    )
    result["fp_table_avg_occupancy"] = ratio(
        int(result["fp_table_occ_sum"]), int(result["busy_cycles"])
    )
    result["commit_backpressure_ratio"] = ratio(
        int(result["commit_backpressure_cycles"]), int(result["busy_cycles"])
    )
    if FULL_FIELDS <= records[0].keys():
        compute_cycles = int(result["phase_compute_cycles"]) + int(
            result["phase_overlap_cycles"]
        )
        result["read_outstanding_avg"] = ratio(
            int(result["read_outstanding_occ_sum"]), int(result["busy_cycles"])
        )
        result["read_outstanding_full_ratio"] = ratio(
            int(result["read_outstanding_full_cycles"]),
            int(result["busy_cycles"]),
        )
        result["compute_overlap_ratio"] = ratio(
            int(result["phase_overlap_cycles"]), compute_cycles
        )
        result["input_phase_ratio"] = ratio(
            int(result["phase_activation_cycles"])
            + int(result["phase_weight_cycles"]),
            int(result["busy_cycles"]),
        )
        result["weight_prefetch_wait_ratio"] = ratio(
            int(result["weight_prefetch_wait_cycles"]),
            int(result["busy_cycles"]),
        )
    if PROBE_FIELDS <= records[0].keys():
        result["profile_result_blocked_ratio"] = ratio(
            int(result["probe_profile_result_blocked_cycles"]),
            int(result["busy_cycles"]),
        )
        result["context_start_blocked_ratio"] = ratio(
            int(result["probe_context_start_blocked_cycles"]),
            int(result["busy_cycles"]),
        )
        result["fp_input_blocked_ratio"] = ratio(
            int(result["probe_fp_input_blocked_cycles"]),
            int(result["busy_cycles"]),
        )
        result["read_response_idle_ratio"] = ratio(
            int(result["probe_read_response_idle_cycles"]),
            int(result["busy_cycles"]),
        )
        result["profile_context_avg_occupancy"] = ratio(
            int(result["probe_profile_context_occ_sum"]),
            int(result["busy_cycles"]),
        )
    return result


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commands-output", type=Path)
    args = parser.parse_args()

    records = parse_log(args.log)
    errors = validate(records)
    if errors:
        raise SystemExit("QBS counter validation failed:\n  " + "\n  ".join(errors))
    write_rows(args.output, [aggregate(args.case, records)])
    if args.commands_output is not None:
        write_rows(args.commands_output, records)
    print(f"wrote {args.output} ({len(records)} commands)")


if __name__ == "__main__":
    main()
