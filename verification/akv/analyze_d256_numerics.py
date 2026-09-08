#!/usr/bin/env python3
"""Isolate Decode accumulation order with real inputs, without changing goldens.

This is a host numerical experiment, not an ISA simulator. In particular it
uses libm expf, not the native RVV vector-exp approximation or host SIMD dot.
"""

import argparse
import ctypes
import ctypes.util
import json
import math
from pathlib import Path
import re
import struct

from run_portability_stage2 import sha, write_json

LIBM = ctypes.CDLL(ctypes.util.find_library("m"))
LIBM.fmaf.argtypes = [ctypes.c_float] * 3
LIBM.fmaf.restype = ctypes.c_float
LIBM.expf.argtypes = [ctypes.c_float]
LIBM.expf.restype = ctypes.c_float


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f16(value):
    return struct.unpack("<e", struct.pack("<e", value))[0]


def tensor(case_dir, relative):
    metadata_path = (case_dir / relative).resolve()
    metadata = json.loads(metadata_path.read_text())
    code, size = {"f16": ("e", 2), "f32": ("f", 4)}[metadata["type"]]
    stride = size
    for dimension, actual in zip(metadata["shape"], metadata["strides"]):
        if actual != stride:
            raise ValueError("diagnostic requires contiguous captured tensors")
        stride *= dimension
    data_path = metadata_path.with_suffix(".bin")
    data = data_path.read_bytes()
    if len(data) != stride or len(data) != metadata["nbytes"]:
        raise ValueError("capture tensor size mismatch")
    return metadata, list(struct.unpack(f"<{len(data) // size}{code}", data)), sha(data_path)


def compute(scores, values, dim, tile_size, half_accumulator):
    """Keep scores fixed; vary only max-update interval and accumulator width."""
    rounded = f16 if half_accumulator else f32
    maximum, total = -math.inf, 0.0
    accum = [0.0] * dim
    changes = []
    for first in range(0, len(scores), tile_size):
        part = scores[first:first + tile_size]
        new_maximum = max(maximum, max(part))
        if new_maximum != maximum:
            changes.append(first + part.index(new_maximum))
        scale = LIBM.expf(f32(maximum - new_maximum))
        accum = [rounded(f32(value * scale)) for value in accum]
        weights = [LIBM.expf(f32(score - new_maximum)) for score in part]
        # Native tiled softmax sums F32 weights into F64 before the F32 store.
        total = f32(f32(total * scale) + math.fsum(weights))
        for token, weight in enumerate(weights, first):
            row = values[token * dim:(token + 1) * dim]
            accum = [rounded(LIBM.fmaf(weight, value, old))
                     for value, old in zip(row, accum)]
        maximum = new_maximum
    inverse = f32(1.0 / total)
    return [f32(value * inverse) for value in accum], changes


def error_summary(actual, golden, atol, rtol):
    errors = [abs(a - b) for a, b in zip(actual, golden)]
    ratios = [e / (atol + rtol * abs(g)) for e, g in zip(errors, golden)]
    failed = [i for i, ratio in enumerate(ratios) if ratio > 1.0]
    return {"mismatches": len(failed), "failed_indices": failed,
            "max_abs_error": max(errors), "max_tolerance_ratio": max(ratios),
            "rmse": math.sqrt(math.fsum(e * e for e in errors) / len(errors))}


def analyze(capture, logs):
    case_dir = capture / "replay/cases/operator/decode/attention_core"
    case = json.loads((case_dir / "case.json").read_text())
    tensors = {role: tensor(case_dir, case[role])
               for role in ("input_a", "key", "value", "mask", "golden")}
    qm, query, _ = tensors["input_a"]
    km, key, _ = tensors["key"]
    vm, value, _ = tensors["value"]
    _, mask, _ = tensors["mask"]
    _, golden, _ = tensors["golden"]
    dim, queries, heads, batches = qm["shape"]
    if dim != 256 or queries != 1 or batches != 1 or km["shape"] != vm["shape"]:
        raise ValueError("expected one D256 Decode query and equal K/V shapes")
    if any(case.get(k) for k in ("logit_softcap", "max_bias", "sinks", "window_enabled")):
        raise ValueError("score features require a separate diagnostic")
    kv_dim, capacity, kv_heads, kv_batches = km["shape"]
    if kv_dim != dim or kv_batches != 1 or heads % kv_heads or len(mask) != capacity:
        raise ValueError("unsupported topology")
    active = next((i for i, v in enumerate(mask) if not math.isfinite(v)), capacity)
    if active == 0 or any(v != -math.inf for v in mask[active:]):
        raise ValueError("expected a finite/-inf prefix mask")
    variants = {"online_f16": (1, True), "tile64_f16": (64, True),
                "online_f32": (1, False), "tile64_f32": (64, False)}
    output = {name: [] for name in variants}
    maxima = {name: [] for name in variants}
    for head in range(heads):
        q = list(map(f16, query[head * dim:(head + 1) * dim]))
        kv_head = head // (heads // kv_heads)
        base = kv_head * capacity * dim
        scores = []
        for token in range(active):
            dot = 0.0
            for d, qi in enumerate(q):
                dot = LIBM.fmaf(qi, key[base + token * dim + d], dot)
            scores.append(f32(f32(dot * case["scale"]) + mask[token]))
        v = value[base:base + active * dim]
        for name, (tile, half) in variants.items():
            result, changes = compute(scores, v, dim, tile, half)
            output[name].extend(result)
            maxima[name].append(changes)
    result = {
        "classification": "host schedule diagnosis; not a replacement golden or RTL PASS",
        "capture": str(capture), "active_kv": active, "dim": dim, "heads": heads,
        "tensor_sha256": {role: data[2] for role, data in tensors.items()},
        "atol": case["atol"], "rtol": case["rtol"],
        "numerics": "F16 Q/K/V; sequential F32 fmaf QK; libm expf; RNE",
        "variants": {name: {**error_summary(values, golden, case["atol"], case["rtol"]),
                             "maximum_update_tokens_per_head": maxima[name]}
                     for name, values in output.items()},
        "rtl_printed_samples": [],
    }
    pattern = re.compile(r"ATTENTION_MISMATCH item=(\d+).*actual=0x([0-9a-f]+) golden=0x([0-9a-f]+)")
    for log in logs:
        samples = []
        for match in pattern.finditer(log.read_text()):
            index = int(match[1])
            actual = struct.unpack("<f", struct.pack("<I", int(match[2], 16)))[0]
            samples.append((index, actual))
        if samples:
            result["rtl_printed_samples"].append({
                "log": str(log), "sha256": sha(log), "samples": len(samples),
                "max_abs_delta_to_host": {
                    name: max(abs(actual - values[index]) for index, actual in samples)
                    for name, values in output.items()},
            })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--rtl-log", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.capture.resolve(), args.rtl_log)
    write_json(args.output, result)
    for name, values in result["variants"].items():
        print(name, "mismatches=", values["mismatches"],
              "max_ratio=", round(values["max_tolerance_ratio"], 5))


if __name__ == "__main__":
    main()
