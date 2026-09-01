#!/usr/bin/env python3
"""Validate captured Prefill Attention against an independent FP32 model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np


TYPE_DTYPES = {
    "f16": np.dtype("<f2"),
    "f32": np.dtype("<f4"),
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contiguous_strides(shape: list[int], element_bytes: int) -> list[int]:
    strides = [element_bytes]
    for dimension in shape[:-1]:
        strides.append(strides[-1] * dimension)
    return strides


def load_tensor(case_dir: Path, relative_path: str, expected_type: str) -> dict:
    metadata_path = (case_dir / relative_path).resolve()
    metadata = load_json(metadata_path)
    tensor_type = str(metadata.get("type", "")).lower()
    if tensor_type != expected_type:
        raise ValueError(
            f"{metadata_path}: expected {expected_type}, got {tensor_type}"
        )
    shape = [int(value) for value in metadata["shape"]]
    strides = [int(value) for value in metadata["strides"]]
    if len(shape) != 4 or any(dimension <= 0 for dimension in shape):
        raise ValueError(f"{metadata_path}: expected a positive 4D shape")
    dtype = TYPE_DTYPES[tensor_type]
    if strides != contiguous_strides(shape, dtype.itemsize):
        raise ValueError(f"{metadata_path}: tensor is not contiguous")
    data_path = metadata_path.with_suffix(".bin")
    expected_bytes = math.prod(shape) * dtype.itemsize
    if int(metadata["nbytes"]) != expected_bytes:
        raise ValueError(f"{metadata_path}: metadata byte count is inconsistent")
    if data_path.stat().st_size != expected_bytes:
        raise ValueError(f"{data_path}: payload byte count is inconsistent")
    # GGML dimension zero is contiguous; reversing the shape produces a
    # conventional NumPy view without moving the captured payload.
    array = np.memmap(
        data_path, dtype=dtype, mode="r", shape=tuple(reversed(shape))
    )
    return {
        "metadata_path": metadata_path,
        "data_path": data_path,
        "shape": shape,
        "array": array,
    }


def causal_prefixes(mask: np.ndarray) -> list[int]:
    prefixes = []
    for row_index, row in enumerate(mask):
        finite = np.isfinite(row)
        prefix = int(np.count_nonzero(finite))
        if prefix == 0 or not np.all(finite[:prefix]):
            raise ValueError(f"mask row {row_index}: visible entries are not a prefix")
        if not np.all(np.isneginf(row[prefix:])):
            raise ValueError(f"mask row {row_index}: blocked tail is not -infinity")
        if not np.all(row[:prefix] == np.float16(0.0)):
            raise ValueError(f"mask row {row_index}: visible prefix is not zero")
        prefixes.append(prefix)
    past_tokens = prefixes[0] - 1
    expected = [past_tokens + index + 1 for index in range(len(prefixes))]
    if prefixes != expected:
        raise ValueError(f"mask prefixes are not causal: {prefixes} != {expected}")
    return prefixes


def update_maximum(record: dict, values: np.ndarray, start_token: int,
                   head: int, name: str) -> None:
    comparable = np.where(np.isfinite(values), values, np.inf)
    flat = int(np.argmax(comparable))
    value = float(comparable.flat[flat])
    if value <= record[name]["value"]:
        return
    token_offset, element = np.unravel_index(flat, values.shape)
    record[name] = {
        "value": value,
        "token": start_token + int(token_offset),
        "head": head,
        "element": int(element),
    }


def validate_case(root: Path, entry: dict, query_block: int) -> dict:
    case_dir = (root / entry["path"]).resolve()
    case_path = case_dir / "case.json"
    case = load_json(case_path)
    if case.get("kind") != "attention_core":
        raise ValueError(f"{case_path}: expected attention_core")
    if bool(case.get("v_transposed", False)):
        raise ValueError(f"{case_path}: transposed V is outside this contract")
    if float(case.get("max_bias", 0.0)) != 0.0:
        raise ValueError(f"{case_path}: ALiBi is outside this contract")
    if float(case.get("logit_softcap", 0.0)) != 0.0:
        raise ValueError(f"{case_path}: logit soft-cap is outside this contract")
    scale = float(case["scale"])
    atol = float(case["atol"])
    rtol = float(case["rtol"])
    if not math.isfinite(scale) or scale <= 0.0 or atol < 0.0 or rtol < 0.0:
        raise ValueError(f"{case_path}: invalid scale or tolerance")

    query_tensor = load_tensor(case_dir, case["input_a"], "f32")
    key_tensor = load_tensor(case_dir, case["key"], "f16")
    value_tensor = load_tensor(case_dir, case["value"], "f16")
    mask_tensor = load_tensor(case_dir, case["mask"], "f16")
    golden_tensor = load_tensor(case_dir, case["golden"], "f32")

    dim, tokens, query_heads, query_batches = query_tensor["shape"]
    key_dim, kv_capacity, kv_heads, key_batches = key_tensor["shape"]
    if query_batches != 1 or key_batches != 1 or key_dim != dim:
        raise ValueError(f"{case_path}: unsupported Query/K topology")
    if value_tensor["shape"] != key_tensor["shape"]:
        raise ValueError(f"{case_path}: K/V topology mismatch")
    if mask_tensor["shape"] != [kv_capacity, tokens, 1, 1]:
        raise ValueError(f"{case_path}: mask topology mismatch")
    if golden_tensor["shape"] != [dim * query_heads, tokens, 1, 1]:
        raise ValueError(f"{case_path}: golden topology mismatch")
    if kv_heads == 0 or query_heads % kv_heads:
        raise ValueError(f"{case_path}: invalid GQA topology")

    query = query_tensor["array"][0]
    key = key_tensor["array"][0]
    value = value_tensor["array"][0]
    mask = mask_tensor["array"][0, 0]
    golden = golden_tensor["array"][0, 0].reshape(tokens, query_heads, dim)
    prefixes = causal_prefixes(mask)

    result = {
        "case_id": entry["id"],
        "case_sha256": sha256(case_path),
        "M_query_tokens": tokens,
        "P_past_tokens": prefixes[0] - 1,
        "head_dim": dim,
        "query_heads": query_heads,
        "kv_heads": kv_heads,
        "gqa_rows": query_heads // kv_heads,
        "kv_capacity": kv_capacity,
        "atol": atol,
        "rtol": rtol,
        "attention_macs": 2 * sum(prefixes) * query_heads * dim,
        "compared_elements": tokens * query_heads * dim,
        "mismatches": 0,
        "nonfinite_results": 0,
        "required_atol_at_rtol": 0.0,
        "max_abs_error": {"value": -1.0},
        "max_tolerance_ratio": {"value": -1.0},
    }
    squared_error_sum = 0.0
    first_mismatch = None
    started = time.monotonic()

    for head in range(query_heads):
        kv_head = head // (query_heads // kv_heads)
        key_f32 = np.asarray(key[kv_head], dtype=np.float32)
        value_f32 = np.asarray(value[kv_head], dtype=np.float32)
        for start in range(0, tokens, query_block):
            end = min(tokens, start + query_block)
            active = prefixes[end - 1]
            query_f32 = np.asarray(query[head, start:end], dtype=np.float32)
            scores = query_f32 @ key_f32[:active].T
            scores *= np.float32(scale)
            scores += np.asarray(mask[start:end, :active], dtype=np.float32)
            scores -= np.max(scores, axis=1, keepdims=True)
            np.exp(scores, out=scores)
            scores /= np.sum(scores, axis=1, keepdims=True, dtype=np.float32)
            actual = scores @ value_f32[:active]
            expected = np.asarray(golden[start:end, head], dtype=np.float32)
            absolute = np.abs(actual - expected)
            tolerance = np.float32(atol) + np.float32(rtol) * np.abs(expected)
            ratio = np.divide(
                absolute,
                tolerance,
                out=np.full_like(absolute, np.inf),
                where=tolerance != 0.0,
            )
            finite = np.isfinite(actual)
            failures = (~finite) | (absolute > tolerance)
            result["mismatches"] += int(np.count_nonzero(failures))
            result["nonfinite_results"] += int(np.count_nonzero(~finite))
            required = np.maximum(
                absolute - np.float32(rtol) * np.abs(expected), 0.0
            )
            result["required_atol_at_rtol"] = max(
                result["required_atol_at_rtol"], float(np.max(required))
            )
            update_maximum(result, absolute, start, head, "max_abs_error")
            update_maximum(
                result, ratio, start, head, "max_tolerance_ratio"
            )
            squared_error_sum += float(
                np.sum(absolute.astype(np.float64) ** 2, dtype=np.float64)
            )
            if first_mismatch is None and np.any(failures):
                token_offset, element = np.argwhere(failures)[0]
                first_mismatch = {
                    "token": start + int(token_offset),
                    "head": head,
                    "element": int(element),
                    "actual": float(actual[token_offset, element]),
                    "golden": float(expected[token_offset, element]),
                    "absolute_error": float(absolute[token_offset, element]),
                    "tolerance": float(tolerance[token_offset, element]),
                }

    result["rms_error"] = math.sqrt(
        squared_error_sum / result["compared_elements"]
    )
    result["first_mismatch"] = first_mismatch
    result["elapsed_seconds"] = time.monotonic() - started
    result["status"] = "PASS" if result["mismatches"] == 0 else "FAIL"
    return result


def validate(root: Path, query_block: int) -> dict:
    root = root.resolve()
    manifest_path = root / "replay" / "manifest.json"
    manifest = load_json(manifest_path)
    cases = [validate_case(root, entry, query_block)
             for entry in manifest["cases"]]
    result = {
        "schema_version": 1,
        "reference": "independent NumPy FP32 stable softmax",
        "capture_root": str(root),
        "manifest_sha256": sha256(manifest_path),
        "query_block": query_block,
        "case_count": len(cases),
        "failed_cases": sum(case["status"] != "PASS" for case in cases),
        "required_atol_at_recorded_rtol": max(
            case["required_atol_at_rtol"] for case in cases
        ),
        "cases": cases,
    }
    result["status"] = "PASS" if result["failed_cases"] == 0 else "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--query-block", type=int, default=16)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    if args.query_block <= 0:
        parser.error("--query-block must be positive")
    result = validate(args.capture_root, args.query_block)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if args.report_only or result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
