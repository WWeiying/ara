#!/usr/bin/env python3
"""Analyze real llama.cpp Prefill Attention captures without changing RTL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import struct
from pathlib import Path


FP16_NEGATIVE_INFINITY = 0xFC00
AKV_MAX_Q_ROWS = 8
AKV_HEAD_DIM_128 = 128
AKV_V2_TILE_TOKENS = 64
AKV_PREFILL_QUERY_BLOCK_TOKENS = 64
AKV_PREFILL_COMPUTE_TILE_TOKENS = 2
AKV_ATTENTION_PLAN_BYTES = 192
RVV_BASELINE_STRATEGIES = frozenset({
    "rvv_qhead_serial",
    "rvv_q64_qhead",
    "rvv_gqa_q4",
    "rvv_gqa_q64",
})
OPERATOR_RESULT_RE = re.compile(
    r"LLAMA_OPERATOR\s+(\S+)\s+(PASS|FAIL)\s+cycles=(\d+)\s+mismatches=(\d+)"
)
AKV_PERF_RE = re.compile(r"^\[AKV_PERF\]\s+(.*)$", re.MULTILINE)
AKV_FIELD_RE = re.compile(r"([a-zA-Z0-9_]+)=(\d+)")
LLM_PERF_REPORT_RE = re.compile(r"^\[LLM_PERF\] wrote (\S+)$", re.MULTILINE)
LLM_PERF_ROW_RE = re.compile(r"^\[LLM_PERF\]\s+(.*)$", re.MULTILINE)
LLM_PERF_FIELD_RE = re.compile(r"([a-zA-Z0-9_]+)=([^ ]+)")
AKV_SUM_FIELDS = (
    "busy_cycles",
    "full",
    "refill",
    "load",
    "release",
    "v2_full",
    "v2_refill",
    "v2_row_load",
    "v2_column_load",
    "q_external_bytes",
    "kv_external_bytes",
    "replay_bytes",
    "replay_backpressure_cycles",
    "read_ranges",
    "translations",
    "ar",
    "r_beats",
    "read_payload_bytes",
    "store_wait_cycles",
    "read_backpressure_cycles",
    "read_outstanding_occ_sum",
    "read_outstanding_full_cycles",
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_tensor(case_dir: Path, relative_path: str, expected_type: str) -> dict:
    metadata_path = (case_dir / relative_path).resolve()
    metadata = load_json(metadata_path)
    data_path = metadata_path.with_suffix(".bin")
    if metadata.get("type", "").lower() != expected_type.lower():
        raise ValueError(
            f"{metadata_path}: expected {expected_type}, got {metadata.get('type')}"
        )
    if not data_path.is_file():
        raise ValueError(f"missing tensor payload: {data_path}")
    payload = data_path.read_bytes()
    if len(payload) != int(metadata["nbytes"]):
        raise ValueError(
            f"{data_path}: payload has {len(payload)} bytes, "
            f"metadata declares {metadata['nbytes']}"
        )
    shape = [int(value) for value in metadata["shape"]]
    strides = [int(value) for value in metadata["strides"]]
    if len(shape) != 4 or len(strides) != 4:
        raise ValueError(f"{metadata_path}: expected four-dimensional tensor")
    return {
        "metadata_path": metadata_path,
        "data_path": data_path,
        "type": metadata["type"].lower(),
        "shape": shape,
        "strides": strides,
        "nbytes": len(payload),
        "payload": payload,
    }


def require_contiguous(tensor: dict, element_bytes: int) -> None:
    shape = tensor["shape"]
    expected = [element_bytes]
    for dimension in range(3):
        expected.append(expected[-1] * shape[dimension])
    if tensor["strides"] != expected:
        raise ValueError(
            f"{tensor['metadata_path']}: unsupported strides "
            f"{tensor['strides']}, expected {expected}"
        )


def active_prefixes(mask: dict, kv_capacity: int, query_tokens: int) -> list[int]:
    values = struct.unpack(f"<{mask['nbytes'] // 2}H", mask["payload"])
    prefixes: list[int] = []
    for token in range(query_tokens):
        row = values[token * kv_capacity : (token + 1) * kv_capacity]
        prefix = 0
        while prefix < kv_capacity and row[prefix] != FP16_NEGATIVE_INFINITY:
            if row[prefix] & 0x7C00 == 0x7C00:
                raise ValueError(
                    f"query token {token} visible mask contains NaN or infinity"
                )
            prefix += 1
        if prefix == 0:
            raise ValueError(f"query token {token} has no visible KV entry")
        if any(value != FP16_NEGATIVE_INFINITY for value in row[prefix:]):
            raise ValueError(
                f"query token {token} mask is not a visible-prefix/blocked-tail mask"
            )
        prefixes.append(prefix)
    return prefixes


def parse_query_tiles(value: str) -> list[int]:
    result = sorted({int(item) for item in value.split(",") if item})
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("query tiles must be positive integers")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_measurement(value: str) -> tuple[str, Path]:
    name, separator, path = value.partition("=")
    if not separator or not name or not path:
        raise argparse.ArgumentTypeError("measurement must be STRATEGY=ARA_LOG")
    return name, Path(path)


def parse_akv_perf(log_text: str) -> dict:
    records = [dict(AKV_FIELD_RE.findall(line)) for line in AKV_PERF_RE.findall(log_text)]
    if not records:
        return {"records": 0}
    for index, record in enumerate(records):
        if record.get("success") != "1" or record.get("fault") != "0":
            raise ValueError(f"AKV command record {index} did not complete successfully")
    aggregate = {field: 0 for field in AKV_SUM_FIELDS}
    for record in records:
        for field in AKV_SUM_FIELDS:
            aggregate[field] += int(record.get(field, 0))
    aggregate["records"] = len(records)
    aggregate["read_outstanding_max"] = max(
        int(record.get("read_outstanding_max", 0)) for record in records
    )
    return aggregate


def parse_llm_perf_report(log_text: str) -> dict:
    rows: dict[str, dict[str, int]] = {}
    case_name = None
    for line in LLM_PERF_ROW_RE.findall(log_text):
        fields = dict(LLM_PERF_FIELD_RE.findall(line))
        phase = fields.pop("phase", None)
        row_case = fields.pop("case", None)
        if phase is None or row_case is None:
            continue
        if case_name is None:
            case_name = row_case
        elif case_name != row_case:
            raise ValueError("LLM performance report mixes multiple cases")
        if phase in rows:
            raise ValueError(f"duplicate LLM performance phase: {phase}")
        try:
            rows[phase] = {key: int(value) for key, value in fields.items()}
        except ValueError as error:
            raise ValueError(f"invalid LLM performance row for phase {phase}") from error
    if not rows:
        raise ValueError("LLM performance report has no counter rows")
    if "total" not in rows:
        raise ValueError("LLM performance report has no total row")

    total = rows["total"]
    cycles = total.get("cycles", 0)
    if cycles <= 0:
        raise ValueError("LLM performance total cycle count must be positive")
    ratios = {
        "backend_busy_ratio": total.get("backend_busy_cycles", 0) / cycles,
        "lane_active_ratio": total.get("lane_active_cycles", 0) / cycles,
        "compute_active_ratio": total.get("compute_active_cycles", 0) / cycles,
        "mfpu_active_ratio": total.get("mfpu_exec_active_cycles", 0) / cycles,
        "request_blocked_ratio": total.get("req_blocked_cycles", 0) / cycles,
        "queue_full_ratio": total.get("queue_full_cycles", 0) / cycles,
        "queue_resource_block_ratio":
            total.get("queue_resource_block_cycles", 0) / cycles,
        "operand_block_ratio": total.get("operand_block_cycles", 0) / cycles,
        "hazard_block_ratio": total.get("hazard_block_cycles", 0) / cycles,
    }
    return {
        "case": case_name,
        "phases": rows,
        "ratios": ratios,
    }


def load_llm_perf(log_path: Path, log_text: str) -> dict:
    report_names = LLM_PERF_REPORT_RE.findall(log_text)
    if not report_names:
        return {}
    if len(report_names) != 1:
        raise ValueError(f"expected one LLM performance report in {log_path}")
    report_name = Path(report_names[0])
    if report_name.is_absolute() or report_name.name != str(report_name):
        raise ValueError(f"unsafe LLM performance report name: {report_name}")
    report_path = log_path.parent / report_name
    if not report_path.is_file():
        raise ValueError(f"missing LLM performance report: {report_path}")
    parsed = parse_llm_perf_report(report_path.read_text(errors="replace"))
    parsed["report"] = str(report_path.resolve())
    parsed["report_sha256"] = sha256(report_path)
    return parsed


def validate_kv_outer_counters(summary: dict, strategy: str, counters: dict) -> dict:
    exact_key = {
        "akv_qblock64_kv_outer": "kv_outer_exact",
        "akv_qblock64_q2_kv_outer": "kv_outer_q2_exact",
    }.get(strategy)
    if exact_key is None:
        return {}
    exact = summary[exact_key]
    expected = {
        "v2_full": exact["v2_full"],
        "v2_refill": exact["v2_refill"],
        "v2_column_load": exact["v2_column_load"],
        "v2_row_load": exact["v2_row_load"],
        "release": exact["v2_release"],
        "q_external_bytes": exact["resident_query_fill_bytes"],
        "kv_external_bytes": exact["external_kv_bytes"],
        "replay_bytes": exact["replay_bytes"],
        "records": exact["command_records"],
    }
    mismatches = {
        field: {"expected": value, "observed": counters.get(field)}
        for field, value in expected.items()
        if counters.get(field) != value
    }
    if mismatches:
        raise ValueError(
            f"{strategy} strict AKV counters do not match the schedule: "
            f"{json.dumps(mismatches, sort_keys=True)}"
        )
    return {
        "strict_counter_status": "PASS",
        "strict_counter_checked_fields": len(expected),
    }


def attach_measurements(
    summary: dict, measurement_specs: list[tuple[str, Path]]
) -> None:
    known = {strategy["name"] for strategy in summary["strategies"]}
    measurements: list[dict] = []
    for strategy, path in measurement_specs:
        path = path.resolve()
        if strategy not in known:
            raise ValueError(f"measurement names unknown strategy: {strategy}")
        if not path.is_file():
            raise ValueError(f"measurement log does not exist: {path}")
        log_text = path.read_text(errors="replace")
        matches = OPERATOR_RESULT_RE.findall(log_text)
        if len(matches) != 1:
            raise ValueError(f"expected one LLAMA_OPERATOR result in {path}")
        case_name, status, cycles, mismatches = matches[0]
        if status != "PASS" or int(mismatches) != 0:
            raise ValueError(f"measurement did not pass: {path}")
        entry = {
            "strategy": strategy,
            "case_name": case_name,
            "cycles": int(cycles),
            "mismatches": int(mismatches),
            "log": str(path),
            "log_sha256": sha256(path),
        }
        llm_perf = load_llm_perf(path, log_text)
        if llm_perf:
            entry["llm_perf"] = llm_perf
            total = llm_perf["phases"]["total"]
            entry.update({f"llm_{key}": value for key, value in total.items()})
            entry.update(
                {f"llm_{key}": value for key, value in llm_perf["ratios"].items()}
            )
            entry["llm_report"] = llm_perf["report"]
            entry["llm_report_sha256"] = llm_perf["report_sha256"]
        counters = parse_akv_perf(log_text)
        entry.update(validate_kv_outer_counters(summary, strategy, counters))
        entry.update({f"akv_{key}": value for key, value in counters.items()})
        measurements.append(entry)
    by_strategy = {entry["strategy"]: entry for entry in measurements}
    ordinary_baseline = by_strategy.get("rvv_qhead_serial")
    if ordinary_baseline is not None:
        for entry in measurements:
            entry["speedup_vs_rvv"] = (
                ordinary_baseline["cycles"] / entry["cycles"]
            )
    measured_rvv_baselines = [
        entry
        for entry in measurements
        if entry["strategy"] in RVV_BASELINE_STRATEGIES
    ]
    strongest_rvv = (
        min(measured_rvv_baselines, key=lambda entry: entry["cycles"])
        if measured_rvv_baselines
        else None
    )
    if strongest_rvv is not None:
        for entry in measurements:
            entry["speedup_vs_strongest_rvv"] = (
                strongest_rvv["cycles"] / entry["cycles"]
            )
    candidate = by_strategy.get("akv_qblock64_kv_outer")
    if candidate is None:
        candidate = by_strategy.get("akv_gqa_serial")
    if strongest_rvv is not None and candidate is not None:
        measured_speedup = strongest_rvv["cycles"] / candidate["cycles"]
        minimum_speedup = summary["decision_gate"]["minimum_kernel_speedup"]
        kernel_gate_pass = measured_speedup >= minimum_speedup
        summary["decision_gate"].update(
            {
                "measurement_status": "PASS",
                "correctness_gate_pass": True,
                "measured_kernel_speedup": measured_speedup,
                "strongest_rvv_strategy": strongest_rvv["strategy"],
                "strongest_rvv_cycles": strongest_rvv["cycles"],
                "kernel_speedup_gate_pass": kernel_gate_pass,
                "model_share_gate_status": "NOT_EVALUATED",
                "overall_status": (
                    "PENDING_MODEL_SHARE"
                    if kernel_gate_pass
                    else "FAIL_KERNEL_SPEEDUP"
                ),
                "next_measurement": (
                    "measure model-level Prefill Attention share and long-Prompt "
                    "ordinary-RVV/tiled-RVV/serial-AKV baselines"
                ),
            }
        )
    summary["measurements"] = measurements


def query_tile_kv_bytes(
    prefixes: list[int], query_tile: int, bytes_per_kv_prefix_token: int
) -> int:
    loaded_prefix_tokens = sum(
        max(prefixes[start : start + query_tile])
        for start in range(0, len(prefixes), query_tile)
    )
    return loaded_prefix_tokens * bytes_per_kv_prefix_token


def analyze(case_path: Path, query_tiles: list[int]) -> dict:
    case_path = case_path.resolve()
    case_dir = case_path.parent
    case = load_json(case_path)
    if case.get("kind") != "attention_core":
        raise ValueError(f"{case_path}: expected attention_core case")
    scale = float(case.get("scale", 0.0))
    max_bias = float(case.get("max_bias", 0.0))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError(f"{case_path}: scale must be finite and positive")
    if max_bias != 0.0:
        raise ValueError(f"{case_path}: nonzero max_bias is not implemented")
    if bool(case.get("v_transposed", False)):
        raise ValueError(f"{case_path}: transposed V is not implemented")

    query = load_tensor(case_dir, case["input_a"], "f32")
    key = load_tensor(case_dir, case["key"], "f16")
    value = load_tensor(case_dir, case["value"], "f16")
    mask = load_tensor(case_dir, case["mask"], "f16")
    golden = load_tensor(case_dir, case["golden"], "f32")
    for tensor, element_bytes in (
        (query, 4),
        (key, 2),
        (value, 2),
        (mask, 2),
        (golden, 4),
    ):
        require_contiguous(tensor, element_bytes)

    head_dim, query_tokens, query_heads, query_batches = query["shape"]
    key_dim, kv_capacity, kv_heads, key_batches = key["shape"]
    if query_tokens <= 1:
        raise ValueError("capture is Decode-like; Prefill requires more than one query token")
    if query_batches != 1 or key_batches != 1:
        raise ValueError("stage-1 analysis supports batch one only")
    if value["shape"] != key["shape"] or key_dim != head_dim:
        raise ValueError("K/V shape or head dimension mismatch")
    if mask["shape"] != [kv_capacity, query_tokens, 1, 1]:
        raise ValueError("mask shape does not match KV capacity and Query tokens")
    if golden["shape"] != [head_dim * query_heads, query_tokens, 1, 1]:
        raise ValueError("golden output shape does not match Query topology")
    if kv_heads <= 0 or query_heads % kv_heads:
        raise ValueError("Query heads must be an integer multiple of KV heads")

    gqa_rows = query_heads // kv_heads
    prefixes = active_prefixes(mask, kv_capacity, query_tokens)
    past_tokens = prefixes[0] - 1
    expected_prefixes = [past_tokens + token + 1 for token in range(query_tokens)]
    if prefixes != expected_prefixes:
        raise ValueError(
            f"mask is prefix-shaped but not causal: {prefixes} != {expected_prefixes}"
        )

    prefix_sum = sum(prefixes)
    bytes_per_kv_prefix_token = kv_heads * head_dim * 2 * 2
    bytes_per_qhead_prefix_token = query_heads * head_dim * 2 * 2
    rvv_qhead_serial_kv_bytes = prefix_sum * query_heads * head_dim * 2 * 2
    gqa_serial_kv_bytes = prefix_sum * bytes_per_kv_prefix_token
    unique_kv_bytes = max(prefixes) * bytes_per_kv_prefix_token
    score_macs = prefix_sum * query_heads * head_dim
    value_macs = score_macs
    query_blocks = []
    for start in range(0, query_tokens, AKV_PREFILL_QUERY_BLOCK_TOKENS):
        count = min(AKV_PREFILL_QUERY_BLOCK_TOKENS, query_tokens - start)
        block_prefix = past_tokens + start + count
        query_blocks.append(
            {
                "start": start,
                "count": count,
                "maximum_prefix": block_prefix,
                "kv_tiles":
                    (block_prefix + AKV_V2_TILE_TOKENS - 1)
                    // AKV_V2_TILE_TOKENS,
            }
        )

    query_tile_visits_per_kv_head = sum(
        (prefix + AKV_V2_TILE_TOKENS - 1) // AKV_V2_TILE_TOKENS
        for prefix in prefixes
    )
    query_tile_visits = query_tile_visits_per_kv_head * kv_heads
    kv_outer_full = len(query_blocks) * kv_heads
    kv_outer_refill = sum(
        block["kv_tiles"] - 1 for block in query_blocks
    ) * kv_heads
    query_group_f32_bytes = gqa_rows * head_dim * 4
    query_group_f16_bytes = gqa_rows * head_dim * 2
    query_conversions = query_tokens * kv_heads
    query_conversion_source_f32_read_bytes = query_conversions * query_group_f32_bytes
    query_workspace_f16_write_bytes = query_conversions * query_group_f16_bytes
    ordinary_qk_query_read_bytes = query_tile_visits * query_group_f16_bytes
    resident_query_fill_bytes = kv_outer_full * query_group_f16_bytes
    total_query_traffic_bytes = (
        query_conversion_source_f32_read_bytes
        + query_workspace_f16_write_bytes
        + ordinary_qk_query_read_bytes
        + resident_query_fill_bytes
    )
    state_scalar_bytes_per_visit = gqa_rows * 2 * 4 * 2
    state_numerator_bytes_per_visit = gqa_rows * head_dim * 4 * 2
    state_rows = query_tokens * query_heads
    active_block_tokens = min(query_tokens, AKV_PREFILL_QUERY_BLOCK_TOKENS)
    active_numerator_f32_bytes = active_block_tokens * gqa_rows * head_dim * 4
    active_softmax_f32_bytes = active_block_tokens * gqa_rows * 2 * 4
    final_output_rw_bytes = query_tokens * query_heads * head_dim * 4 * 2
    final_softmax_sum_read_bytes = state_rows * 4
    initial_state_write_bytes = (
        query_tokens * query_heads * (head_dim * 4 + 2 * 4)
    )
    active_local_workspace_bytes = (
        active_block_tokens * query_group_f16_bytes
        + AKV_ATTENTION_PLAN_BYTES
        + AKV_PREFILL_COMPUTE_TILE_TOKENS
        * gqa_rows * AKV_V2_TILE_TOKENS * 4
        + active_block_tokens * gqa_rows * 2 * 4
        + AKV_PREFILL_COMPUTE_TILE_TOKENS * gqa_rows * 4
    )
    allocated_workspace_bytes = (
        AKV_MAX_Q_ROWS * AKV_PREFILL_QUERY_BLOCK_TOKENS
        * AKV_HEAD_DIM_128 * 2
        + AKV_ATTENTION_PLAN_BYTES
        + AKV_PREFILL_COMPUTE_TILE_TOKENS
        * AKV_MAX_Q_ROWS * AKV_V2_TILE_TOKENS * 4
        + AKV_PREFILL_QUERY_BLOCK_TOKENS * AKV_MAX_Q_ROWS * 2 * 4
        + AKV_PREFILL_COMPUTE_TILE_TOKENS * AKV_MAX_Q_ROWS * 4
    )
    allocated_workspace_bytes = (
        (allocated_workspace_bytes + 63) // 64
    ) * 64
    block_prefix_sum = sum(block["maximum_prefix"] for block in query_blocks)
    qblock_external_kv_bytes = block_prefix_sum * bytes_per_kv_prefix_token
    column_replay_tokens_per_kv_head = 0
    for block in query_blocks:
        for token in range(block["start"], block["start"] + block["count"]):
            for tile_start in range(0, prefixes[token], AKV_V2_TILE_TOKENS):
                column_replay_tokens_per_kv_head += min(
                    AKV_V2_TILE_TOKENS,
                    block["maximum_prefix"] - tile_start,
                )
    column_replay_bytes = (
        column_replay_tokens_per_kv_head * kv_heads * head_dim * 2
    )
    row_replay_bytes = prefix_sum * kv_heads * head_dim * 2
    kv_outer_replay_bytes = column_replay_bytes + row_replay_bytes
    kv_outer_release = kv_outer_full
    kv_outer_command_records = (
        kv_outer_full
        + kv_outer_refill
        + query_tile_visits * head_dim
        + prefix_sum * kv_heads
        + kv_outer_release
    )

    q2_group_visits_per_kv_head = 0
    q2_column_replay_tokens_per_kv_head = 0
    for block in query_blocks:
        block_start = block["start"]
        block_count = block["count"]
        block_end = block_start + block_count
        pair_count = (
            block_count + AKV_PREFILL_COMPUTE_TILE_TOKENS - 1
        ) // AKV_PREFILL_COMPUTE_TILE_TOKENS
        for tile_start in range(0, block["maximum_prefix"], AKV_V2_TILE_TOKENS):
            first_active = max(block_start, tile_start - past_tokens)
            if first_active >= block_end:
                continue
            first_active_local = first_active - block_start
            first_active_pair = (
                first_active_local // AKV_PREFILL_COMPUTE_TILE_TOKENS
            )
            active_groups = pair_count - first_active_pair
            resident_tokens = min(
                AKV_V2_TILE_TOKENS, block["maximum_prefix"] - tile_start
            )
            q2_group_visits_per_kv_head += active_groups
            q2_column_replay_tokens_per_kv_head += (
                active_groups * resident_tokens
            )
    q2_group_visits = q2_group_visits_per_kv_head * kv_heads
    q2_column_replay_bytes = (
        q2_column_replay_tokens_per_kv_head * kv_heads * head_dim * 2
    )
    q2_replay_bytes = q2_column_replay_bytes + row_replay_bytes
    q2_command_records = (
        kv_outer_full
        + kv_outer_refill
        + q2_group_visits * head_dim
        + prefix_sum * kv_heads
        + kv_outer_release
    )

    strategies = [
        {
            "name": "rvv_qhead_serial",
            "query_tile": 1,
            "external_kv_bytes": rvv_qhead_serial_kv_bytes,
            "required_q_rows_if_concurrent": 1,
            "fits_current_q_rows": True,
        },
        {
            "name": "rvv_q64_qhead",
            "query_tile": AKV_PREFILL_QUERY_BLOCK_TOKENS,
            "external_kv_bytes": query_tile_kv_bytes(
                prefixes,
                AKV_PREFILL_QUERY_BLOCK_TOKENS,
                bytes_per_qhead_prefix_token,
            ),
            "required_q_rows_if_concurrent": AKV_PREFILL_QUERY_BLOCK_TOKENS,
            "fits_current_q_rows": False,
            "query_mode": "standard_rvv_per_qhead_q64_software_tile",
        },
        {
            "name": "rvv_gqa_q4",
            "query_tile": 4,
            "external_kv_bytes": query_tile_kv_bytes(
                prefixes, 4, bytes_per_kv_prefix_token
            ),
            "required_q_rows_if_concurrent": 4 * gqa_rows,
            "fits_current_q_rows": False,
            "query_mode": "standalone_standard_rvv_gqa_tile",
        },
        {
            "name": "rvv_gqa_q64",
            "query_tile": AKV_PREFILL_QUERY_BLOCK_TOKENS,
            "external_kv_bytes": query_tile_kv_bytes(
                prefixes,
                AKV_PREFILL_QUERY_BLOCK_TOKENS,
                bytes_per_kv_prefix_token,
            ),
            "required_q_rows_if_concurrent": (
                AKV_PREFILL_QUERY_BLOCK_TOKENS * gqa_rows
            ),
            "fits_current_q_rows": False,
            "query_mode": "standard_rvv_gqa_q64_software_tile",
        },
        {
            "name": "akv_gqa_serial",
            "query_tile": 1,
            "external_kv_bytes": gqa_serial_kv_bytes,
            "required_q_rows_if_concurrent": gqa_rows,
            "fits_current_q_rows": gqa_rows <= AKV_MAX_Q_ROWS,
        },
        {
            "name": "akv_qblock64_kv_outer",
            "query_tile": AKV_PREFILL_QUERY_BLOCK_TOKENS,
            "external_kv_bytes": qblock_external_kv_bytes,
            "required_q_rows_if_concurrent": gqa_rows,
            "fits_current_q_rows": gqa_rows <= AKV_MAX_Q_ROWS,
            "query_mode": "fixed_software_query_block",
        },
        {
            "name": "akv_qblock64_q2_kv_outer",
            "query_tile": AKV_PREFILL_QUERY_BLOCK_TOKENS,
            "external_kv_bytes": qblock_external_kv_bytes,
            "required_q_rows_if_concurrent": gqa_rows,
            "fits_current_q_rows": gqa_rows <= AKV_MAX_Q_ROWS,
            "implemented_fast_path": (
                head_dim == AKV_HEAD_DIM_128 and gqa_rows == 6
            ),
            "query_mode": "fixed_query_block_two_query_k_column_reuse",
        },
    ]
    for query_tile in query_tiles:
        rows = query_tile * gqa_rows
        strategies.append(
            {
                "name": f"akv_query_tile_{query_tile}",
                "query_tile": query_tile,
                "external_kv_bytes": query_tile_kv_bytes(
                    prefixes, query_tile, bytes_per_kv_prefix_token
                ),
                "required_q_rows_if_concurrent": rows,
                "fits_current_q_rows": rows <= AKV_MAX_Q_ROWS,
            }
        )
    strategies.append(
        {
            "name": "unique_kv_floor",
            "query_tile": query_tokens,
            "external_kv_bytes": unique_kv_bytes,
            "required_q_rows_if_concurrent": query_tokens * gqa_rows,
            "fits_current_q_rows": query_tokens * gqa_rows <= AKV_MAX_Q_ROWS,
        }
    )

    for strategy in strategies:
        query_tile = strategy["query_tile"]
        rows = strategy["required_q_rows_if_concurrent"]
        score_slots = 1
        if strategy["name"] == "akv_qblock64_q2_kv_outer":
            score_slots = AKV_PREFILL_COMPUTE_TILE_TOKENS
        state_rows_for_strategy = rows
        if strategy["name"] in {
            "akv_qblock64_kv_outer",
            "akv_qblock64_q2_kv_outer",
        }:
            state_rows_for_strategy = active_block_tokens * gqa_rows
        strategy["reduction_vs_rvv"] = (
            rvv_qhead_serial_kv_bytes / strategy["external_kv_bytes"]
        )
        strategy["reduction_vs_akv_serial"] = (
            gqa_serial_kv_bytes / strategy["external_kv_bytes"]
        )
        strategy["query_context_f16_bytes"] = (
            state_rows_for_strategy * head_dim * 2
        )
        strategy["concurrent_numerator_state_f32_bytes"] = (
            state_rows_for_strategy * head_dim * 4
        )
        strategy["score_f32_bytes"] = (
            score_slots * rows * AKV_V2_TILE_TOKENS * 4
        )
        strategy["concurrent_softmax_working_f32_bytes"] = (
            state_rows_for_strategy * 2 * 4 + score_slots * rows * 4
        )
        strategy["conceptual_concurrent_state_bytes"] = (
            strategy["query_context_f16_bytes"]
            + strategy["concurrent_numerator_state_f32_bytes"]
            + strategy["score_f32_bytes"]
            + strategy["concurrent_softmax_working_f32_bytes"]
        )
        strategy["requires_query_only_context_update"] = False
        strategy["requires_concurrent_query_state"] = strategy["name"].startswith(
            "akv_query_tile_"
        ) or strategy["name"] in {
            "unique_kv_floor",
            "akv_qblock64_kv_outer",
            "akv_qblock64_q2_kv_outer",
        }

    return {
        "schema_version": 4,
        "status": "PASS",
        "scope": "real-capture static Prefill Attention work/traffic/state analysis",
        "case": str(case_path),
        "provenance": {
            "case_sha256": sha256(case_path),
            "query_sha256": sha256(query["data_path"]),
            "key_sha256": sha256(key["data_path"]),
            "value_sha256": sha256(value["data_path"]),
            "mask_sha256": sha256(mask["data_path"]),
            "golden_sha256": sha256(golden["data_path"]),
        },
        "operator": {
            "scale": scale,
            "max_bias": max_bias,
            "v_transposed": False,
            "atol": float(case.get("atol", 0.0)),
            "rtol": float(case.get("rtol", 0.0)),
        },
        "shape": {
            "head_dim": head_dim,
            "query_tokens": query_tokens,
            "query_heads": query_heads,
            "kv_heads": kv_heads,
            "gqa_rows": gqa_rows,
            "batch": 1,
            "kv_capacity": kv_capacity,
            "past_tokens": past_tokens,
            "active_prefixes": prefixes,
        },
        "work": {
            "active_query_kv_pairs_per_head": prefix_sum,
            "active_query_head_kv_pairs": prefix_sum * query_heads,
            "score_macs": score_macs,
            "value_macs": value_macs,
            "attention_macs": score_macs + value_macs,
        },
        "payload": {
            "query_f32_bytes": query["nbytes"],
            "query_f16_context_bytes": query_tokens * query_heads * head_dim * 2,
            "mask_physical_bytes": mask["nbytes"],
            "output_f32_bytes": golden["nbytes"],
            "unique_visible_kv_bytes": unique_kv_bytes,
        },
        "kv_outer_exact": {
            "query_block_tokens": AKV_PREFILL_QUERY_BLOCK_TOKENS,
            "query_block_count": len(query_blocks),
            "query_blocks": query_blocks,
            "block_maximum_prefix_sum": block_prefix_sum,
            "query_tile_visits_per_kv_head": query_tile_visits_per_kv_head,
            "query_tile_visits": query_tile_visits,
            "v2_full": kv_outer_full,
            "v2_refill": kv_outer_refill,
            "query_conversions": query_conversions,
            "query_group_f32_bytes": query_group_f32_bytes,
            "query_group_f16_bytes": query_group_f16_bytes,
            "query_conversion_source_f32_read_bytes":
                query_conversion_source_f32_read_bytes,
            "query_workspace_f16_write_bytes": query_workspace_f16_write_bytes,
            "ordinary_qk_query_read_bytes": ordinary_qk_query_read_bytes,
            "resident_query_fill_bytes": resident_query_fill_bytes,
            "total_query_traffic_bytes": total_query_traffic_bytes,
            "external_kv_bytes": qblock_external_kv_bytes,
            "v2_column_load": query_tile_visits * head_dim,
            "v2_row_load": prefix_sum * kv_heads,
            "v2_release": kv_outer_release,
            "column_replay_bytes": column_replay_bytes,
            "row_replay_bytes": row_replay_bytes,
            "replay_bytes": kv_outer_replay_bytes,
            "command_records": kv_outer_command_records,
            "active_output_numerator_f32_bytes": active_numerator_f32_bytes,
            "active_softmax_state_f32_bytes": active_softmax_f32_bytes,
            "state_scalar_read_write_bytes": query_tile_visits
            * state_scalar_bytes_per_visit,
            "state_numerator_read_write_bytes": query_tile_visits
            * state_numerator_bytes_per_visit,
            "initial_state_write_bytes": initial_state_write_bytes,
            "final_output_read_write_bytes": final_output_rw_bytes,
            "final_softmax_sum_read_bytes": final_softmax_sum_read_bytes,
            "active_local_workspace_bytes": active_local_workspace_bytes,
            "allocated_workspace_bytes": allocated_workspace_bytes,
            "workspace_semantics": (
                "fixed 64-Query cache plus plan, two score/scale scratch slots, "
                "and online-softmax state; output holds only the current "
                "block's F32 numerator"
            ),
        },
        "kv_outer_q2_exact": {
            "compute_tile_tokens": AKV_PREFILL_COMPUTE_TILE_TOKENS,
            "supported_shape": (
                head_dim == AKV_HEAD_DIM_128 and gqa_rows == 6
            ),
            "query_group_visits_per_kv_head": q2_group_visits_per_kv_head,
            "query_group_visits": q2_group_visits,
            "v2_full": kv_outer_full,
            "v2_refill": kv_outer_refill,
            "v2_column_load": q2_group_visits * head_dim,
            "v2_row_load": prefix_sum * kv_heads,
            "v2_release": kv_outer_release,
            "resident_query_fill_bytes": resident_query_fill_bytes,
            "external_kv_bytes": qblock_external_kv_bytes,
            "column_replay_bytes": q2_column_replay_bytes,
            "row_replay_bytes": row_replay_bytes,
            "replay_bytes": q2_replay_bytes,
            "command_records": q2_command_records,
            "schedule_semantics": (
                "fixed adjacent Query pairs share each K-column replay; odd "
                "tails and a pair with only one visible Query execute as Q1; "
                "V-row replay remains per Query token"
            ),
        },
        "strategies": strategies,
        "decision_gate": {
            "rtl_changed": True,
            "next_measurement": (
                "validate the fixed B64 schedule on the short discriminator, then "
                "measure a multi-tile point and the required M>=512 real capture"
            ),
            "minimum_kernel_speedup": 1.2,
            "minimum_model_share": 0.1,
        },
    }


def write_outputs(summary: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "strategies.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "name",
            "query_tile",
            "external_kv_bytes",
            "reduction_vs_rvv",
            "reduction_vs_akv_serial",
            "required_q_rows_if_concurrent",
            "fits_current_q_rows",
            "query_context_f16_bytes",
            "concurrent_numerator_state_f32_bytes",
            "score_f32_bytes",
            "concurrent_softmax_working_f32_bytes",
            "conceptual_concurrent_state_bytes",
            "requires_query_only_context_update",
            "requires_concurrent_query_state",
        ]
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(summary["strategies"])
    with (output_dir / "measurements.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fieldnames = [
            "strategy",
            "case_name",
            "cycles",
            "mismatches",
            "speedup_vs_rvv",
            "speedup_vs_strongest_rvv",
            "strict_counter_status",
            "strict_counter_checked_fields",
            "akv_records",
            "akv_busy_cycles",
            "akv_v2_full",
            "akv_v2_refill",
            "akv_v2_row_load",
            "akv_v2_column_load",
            "akv_release",
            "akv_q_external_bytes",
            "akv_kv_external_bytes",
            "akv_replay_bytes",
            "akv_replay_backpressure_cycles",
            "akv_read_ranges",
            "akv_ar",
            "akv_r_beats",
            "akv_read_payload_bytes",
            "akv_read_backpressure_cycles",
            "akv_read_outstanding_occ_sum",
            "akv_read_outstanding_max",
            "akv_read_outstanding_full_cycles",
            "llm_backend_busy_cycles",
            "llm_lane_active_cycles",
            "llm_compute_active_cycles",
            "llm_mfpu_exec_active_cycles",
            "llm_mfpu_exec_lane_fires",
            "llm_req_valid_cycles",
            "llm_req_fire_count",
            "llm_req_blocked_cycles",
            "llm_queue_full_cycles",
            "llm_queue_resource_block_cycles",
            "llm_operand_block_cycles",
            "llm_hazard_block_cycles",
            "llm_backend_busy_ratio",
            "llm_lane_active_ratio",
            "llm_compute_active_ratio",
            "llm_mfpu_active_ratio",
            "llm_request_blocked_ratio",
            "llm_queue_full_ratio",
            "llm_queue_resource_block_ratio",
            "llm_operand_block_ratio",
            "llm_hazard_block_ratio",
            "llm_report",
            "llm_report_sha256",
            "log",
            "log_sha256",
        ]
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(summary.get("measurements", []))
    (output_dir / "complete").touch()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--query-tiles", type=parse_query_tiles, default=[2, 4])
    parser.add_argument(
        "--measurement",
        action="append",
        type=parse_measurement,
        default=[],
        metavar="STRATEGY=ARA_LOG",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    summary = analyze(args.case, args.query_tiles)
    attach_measurements(summary, args.measurement)
    if args.output_dir is not None:
        write_outputs(summary, args.output_dir)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
