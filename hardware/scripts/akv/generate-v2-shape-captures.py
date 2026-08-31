#!/usr/bin/env python3

"""Generate AKV-v2 numerical cases from captured Qwen attention tensors.

These cases are derived-real verification stimuli, not additional model-native
shapes. D64 uses a prefix of each captured D128 row, and KV lengths beyond the
capture repeat source token rows. The generated metadata records both facts.
"""

import argparse
import json
import math
import struct
from pathlib import Path


DEFAULT_SOURCE = Path(
    "/home/wangwy/llama/captures/"
    "qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv256"
)
DEFAULT_OUTPUT = Path(
    "/home/wangwy/llama/captures/akv-v2-derived-real-qwen"
)
HEAD_DIMS = (64, 128)
Q_ROWS = (1, 4, 6, 8)
KV_LENGTHS = (16, 63, 64, 65, 128, 256, 1024)


def read_json(path):
    return json.loads(path.read_text())


def resolve_tensor(case_dir, case, key):
    meta_path = (case_dir / case[key]).resolve()
    meta = read_json(meta_path)
    data_path = meta_path.with_suffix(".bin")
    data = data_path.read_bytes()
    if len(data) != int(meta["nbytes"]):
        raise SystemExit(f"invalid tensor pair: {meta_path}")
    return meta, data


def f16(value):
    return struct.unpack("<e", struct.pack("<e", float(value)))[0]


def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def f32_mul(lhs, rhs):
    return f32(lhs * rhs)


def f32_fma(lhs, rhs, addend):
    # The inputs are exact F32/F16 values. Binary64 can represent their exact
    # product and sum here, followed by the single rounding done by fmadd.s.
    return f32(lhs * rhs + addend)


def unpack_f32(data):
    return [item[0] for item in struct.iter_unpack("<f", data)]


def unpack_f16(data):
    return [item[0] for item in struct.iter_unpack("<e", data)]


def write_tensor(directory, name, tensor_type, shape, values, code):
    data_path = directory / f"{name}.bin"
    meta_path = directory / f"{name}.json"
    data = b"".join(struct.pack(code, value) for value in values)
    data_path.write_bytes(data)
    strides = []
    stride = struct.calcsize(code)
    for extent in shape:
        strides.append(stride)
        stride *= extent
    meta_path.write_text(json.dumps({
        "role": name,
        "tensor_name": name,
        "type": tensor_type,
        "shape": shape,
        "strides": strides,
        "nbytes": len(data),
    }, indent=2) + "\n")
    return meta_path.name


def attention_golden(query, key, value, q_rows, head_dim, kv_length, scale):
    output = []
    for row in range(q_rows):
        q_base = row * head_dim
        query_f16 = [f16(query[q_base + dim]) for dim in range(head_dim)]
        accumulator = [f16(0.0)] * head_dim
        maximum = -math.inf
        sum_weights = f32(0.0)
        for token in range(kv_length):
            kv_base = token * head_dim
            dot = 0.0
            for dim in range(head_dim):
                # The scalar ELF rounds each product with fmul.s before
                # promoting it into the binary64 dot-product accumulator.
                dot += f32_mul(query_f16[dim], key[kv_base + dim])
            score = f32_fma(f32(dot), scale, f32(0.0))
            old_maximum = maximum
            old_scale = f32(1.0)
            weight = f32(1.0)
            if score > maximum:
                maximum = score
                old_scale = (f32(0.0) if math.isinf(old_maximum)
                             else f32(math.exp(old_maximum - maximum)))
                for dim in range(head_dim):
                    accumulator[dim] = f16(
                        f32_mul(accumulator[dim], old_scale)
                    )
            else:
                weight = f32(math.exp(score - maximum))
            for dim in range(head_dim):
                accumulator[dim] = f16(
                    f32_fma(value[kv_base + dim], weight, accumulator[dim])
                )
            sum_weights = f32_fma(sum_weights, old_scale, weight)
        inverse = f32(0.0 if sum_weights == 0.0 else f32(1.0) / sum_weights)
        for dim in range(head_dim):
            output.append(f32_mul(accumulator[dim], inverse))
    return output


def build_case(source_q, source_k, source_v, source_dim, source_kv,
               source_q_heads, head_dim, q_rows, kv_length, output_root):
    if head_dim > source_dim or q_rows > source_q_heads:
        raise SystemExit("source capture is smaller than requested derived shape")

    query = []
    for row in range(q_rows):
        base = row * source_dim
        query.extend(source_q[base:base + head_dim])

    key = []
    value = []
    for token in range(kv_length):
        source_token = token % source_kv
        base = source_token * source_dim
        key.extend(source_k[base:base + head_dim])
        value.extend(source_v[base:base + head_dim])

    scale = f32(1.0 / math.sqrt(head_dim))
    golden = attention_golden(
        query, key, value, q_rows, head_dim, kv_length, scale
    )
    case_id = f"akv-v2/derived-real/d{head_dim}-g{q_rows}-kv{kv_length}"
    relative = Path("replay/cases") / case_id
    directory = output_root / relative
    directory.mkdir(parents=True, exist_ok=True)

    input_name = write_tensor(
        directory, "query", "f32", [head_dim, 1, q_rows, 1],
        query, "<f"
    )
    key_name = write_tensor(
        directory, "key", "f16", [head_dim, kv_length, 1, 1],
        key, "<e"
    )
    value_name = write_tensor(
        directory, "value", "f16", [head_dim, kv_length, 1, 1],
        value, "<e"
    )
    mask_name = write_tensor(
        directory, "mask", "f16", [kv_length, 1, 1, 1],
        [0.0] * kv_length, "<e"
    )
    golden_name = write_tensor(
        directory, "golden", "f32", [head_dim, q_rows, 1, 1],
        golden, "<f"
    )
    (directory / "case.json").write_text(json.dumps({
        "kind": "attention_core",
        "input_a": input_name,
        "key": key_name,
        "value": value_name,
        "mask": mask_name,
        "golden": golden_name,
        "scale": scale,
        "max_bias": 0.0,
        "v_transposed": False,
        "atol": 0.02,
        "rtol": 0.02,
        "provenance": {
            "classification": "derived-real verification stimulus",
            "d64_is_dimension_prefix": head_dim == 64,
            "kv_rows_repeat_after": source_kv if kv_length > source_kv else 0,
        },
    }, indent=2) + "\n")
    return {
        "id": case_id,
        "level": "operator-leaf",
        "kind": "attention_core",
        "path": str(relative),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_case_dir = (
        args.source_root / "replay/cases/operator/decode/attention_core"
    )
    case = read_json(source_case_dir / "case.json")
    q_meta, q_data = resolve_tensor(source_case_dir, case, "input_a")
    k_meta, k_data = resolve_tensor(source_case_dir, case, "key")
    v_meta, v_data = resolve_tensor(source_case_dir, case, "value")
    source_dim = int(q_meta["shape"][0])
    source_q_heads = int(q_meta["shape"][2])
    source_kv = int(k_meta["shape"][1])
    source_kv_heads = int(k_meta["shape"][2])
    if source_kv_heads < 1 or int(v_meta["shape"][2]) < 1:
        raise SystemExit("source capture contains no KV head")

    # Select KV head zero. Tensor storage is dimension, token, then KV head.
    source_q = unpack_f32(q_data)
    source_k_all = unpack_f16(k_data)
    source_v_all = unpack_f16(v_data)
    per_kv_head = source_dim * source_kv
    source_k = source_k_all[:per_kv_head]
    source_v = source_v_all[:per_kv_head]

    args.output.mkdir(parents=True, exist_ok=True)
    entries = []
    for head_dim in HEAD_DIMS:
        for q_rows in Q_ROWS:
            for kv_length in KV_LENGTHS:
                entries.append(build_case(
                    source_q, source_k, source_v, source_dim, source_kv,
                    source_q_heads, head_dim, q_rows, kv_length, args.output
                ))

    manifest_dir = args.output / "replay"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M derived AKV-v2 matrix",
        "source": str(args.source_root),
        "classification": "derived-real verification stimuli; not model-native shapes",
        "cases": entries,
    }, indent=2) + "\n")
    print(f"wrote {len(entries)} cases to {args.output}")


if __name__ == "__main__":
    main()
