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
AKV_V2_TILE_TOKENS = 64
OPERATOR_RESULT_RE = re.compile(
    r"LLAMA_OPERATOR\s+(\S+)\s+(PASS|FAIL)\s+cycles=(\d+)\s+mismatches=(\d+)"
)
AKV_PERF_RE = re.compile(r"^\[AKV_PERF\]\s+(.*)$", re.MULTILINE)
AKV_FIELD_RE = re.compile(r"([a-zA-Z0-9_]+)=(\d+)")
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
        entry.update(
            {f"akv_{key}": value for key, value in parse_akv_perf(log_text).items()}
        )
        measurements.append(entry)
    by_strategy = {entry["strategy"]: entry for entry in measurements}
    baseline = by_strategy.get("rvv_qhead_serial")
    if baseline is not None:
        for entry in measurements:
            entry["speedup_vs_rvv"] = baseline["cycles"] / entry["cycles"]
    candidate = by_strategy.get("akv_gqa_serial")
    if baseline is not None and candidate is not None:
        measured_speedup = baseline["cycles"] / candidate["cycles"]
        minimum_speedup = summary["decision_gate"]["minimum_kernel_speedup"]
        kernel_gate_pass = measured_speedup >= minimum_speedup
        summary["decision_gate"].update(
            {
                "measurement_status": "PASS",
                "correctness_gate_pass": True,
                "measured_kernel_speedup": measured_speedup,
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
    rvv_qhead_serial_kv_bytes = prefix_sum * query_heads * head_dim * 2 * 2
    gqa_serial_kv_bytes = prefix_sum * bytes_per_kv_prefix_token
    unique_kv_bytes = max(prefixes) * bytes_per_kv_prefix_token
    score_macs = prefix_sum * query_heads * head_dim
    value_macs = score_macs

    strategies = [
        {
            "name": "rvv_qhead_serial",
            "query_tile": 1,
            "external_kv_bytes": rvv_qhead_serial_kv_bytes,
            "required_q_rows_if_concurrent": 1,
            "fits_current_q_rows": True,
        },
        {
            "name": "akv_gqa_serial",
            "query_tile": 1,
            "external_kv_bytes": gqa_serial_kv_bytes,
            "required_q_rows_if_concurrent": gqa_rows,
            "fits_current_q_rows": gqa_rows <= AKV_MAX_Q_ROWS,
        },
    ]
    if max(prefixes) <= AKV_V2_TILE_TOKENS:
        strategies.append(
            {
                "name": "akv_resident_single_kv_tile",
                "query_tile": 1,
                "external_kv_bytes": unique_kv_bytes,
                "required_q_rows_if_concurrent": gqa_rows,
                "fits_current_q_rows": gqa_rows <= AKV_MAX_Q_ROWS,
            }
        )
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
        strategy["reduction_vs_rvv"] = (
            rvv_qhead_serial_kv_bytes / strategy["external_kv_bytes"]
        )
        strategy["reduction_vs_akv_serial"] = (
            gqa_serial_kv_bytes / strategy["external_kv_bytes"]
        )
        strategy["query_context_f16_bytes"] = rows * head_dim * 2
        strategy["accumulator_f16_bytes"] = rows * head_dim * 2
        strategy["score_f32_bytes"] = rows * AKV_V2_TILE_TOKENS * 4
        strategy["softmax_scalar_bytes"] = rows * 3 * 4
        strategy["workspace_bytes"] = (
            strategy["accumulator_f16_bytes"]
            + strategy["score_f32_bytes"]
            + strategy["softmax_scalar_bytes"]
        )
        strategy["requires_query_only_context_update"] = strategy["name"] in {
            "akv_resident_single_kv_tile",
        }
        strategy["requires_concurrent_query_state"] = strategy["name"].startswith(
            "akv_query_tile_"
        ) or strategy["name"] == "unique_kv_floor"

    return {
        "schema_version": 1,
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
        "strategies": strategies,
        "decision_gate": {
            "rtl_changed": False,
            "next_measurement": (
                "measure ordinary RVV and existing-command serial AKV cycles; only then "
                "evaluate a Query-only context-update command"
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
            "workspace_bytes",
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
