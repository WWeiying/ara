#!/usr/bin/env python3

"""Validate and package one real llama.cpp Decode attention capture."""

import argparse
import json
import math
import struct
from pathlib import Path


TENSOR_STEMS = {
    "input_a": "attn_q_input-0",
    "key": "attn_k_input-0",
    "value": "attn_v_input-0",
    "mask": "attn_mask_input-0",
    "golden": "kqv_out-0",
}

ATTENTION_PARAMS_STEM = "attention_params-0"


def load_tensor(block: Path, stem: str) -> dict:
    metadata_path = block / f"{stem}.json"
    data_path = block / f"{stem}.bin"
    if not metadata_path.is_file() or not data_path.is_file():
        raise SystemExit(f"missing capture tensor pair: {stem}")
    metadata = json.loads(metadata_path.read_text())
    if data_path.stat().st_size != int(metadata["nbytes"]):
        raise SystemExit(f"size mismatch for {data_path}")
    return metadata


def active_mask_prefix(path: Path, capacity: int) -> int:
    data = path.read_bytes()
    if len(data) != capacity * 2:
        raise SystemExit(f"invalid attention mask size: {len(data)}")
    values = struct.unpack(f"<{capacity}H", data)
    active = 0
    while active < capacity and values[active] == 0x0000:
        active += 1
    if active == 0:
        raise SystemExit("attention mask has no active KV entries")
    if any(value != 0xFC00 for value in values[active:]):
        raise SystemExit("attention mask is not a 0/-inf prefix mask")
    return active


def relative_tensor_path(stem: str) -> str:
    return f"../../../../../decode/block/{stem}.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--source", default="real host llama.cpp decode inference")
    parser.add_argument("--scale", type=float)
    parser.add_argument("--atol", type=float, default=0.004)
    parser.add_argument("--rtol", type=float, default=0.002)
    args = parser.parse_args()

    root = args.capture_root.resolve()
    block = root / "decode" / "block"
    tensors = {
        role: load_tensor(block, stem)
        for role, stem in TENSOR_STEMS.items()
    }

    query = tensors["input_a"]
    key = tensors["key"]
    value = tensors["value"]
    mask = tensors["mask"]
    golden = tensors["golden"]
    q_shape = list(map(int, query["shape"]))
    k_shape = list(map(int, key["shape"]))
    v_shape = list(map(int, value["shape"]))
    mask_shape = list(map(int, mask["shape"]))
    golden_shape = list(map(int, golden["shape"]))

    head_dim, query_tokens, query_heads, query_batches = q_shape
    key_dim, kv_capacity, kv_heads, key_batches = k_shape
    if query["type"] != "f32" or key["type"] != "f16" or value["type"] != "f16":
        raise SystemExit("attention capture must use F32 Q and F16 K/V")
    if mask["type"] != "f16" or golden["type"] != "f32":
        raise SystemExit("attention capture must use F16 mask and F32 output")
    if query_tokens != 1 or query_batches != 1 or key_batches != 1:
        raise SystemExit("only batch-one Decode captures are packageable")
    if v_shape != k_shape or key_dim != head_dim:
        raise SystemExit("K/V shape or head dimension mismatch")
    if mask_shape != [kv_capacity, 1, 1, 1]:
        raise SystemExit("attention mask shape does not match KV capacity")
    if kv_heads <= 0 or query_heads % kv_heads != 0:
        raise SystemExit("query heads must be an integer multiple of KV heads")
    gqa_rows = query_heads // kv_heads
    if gqa_rows < 1 or gqa_rows > 8:
        raise SystemExit(f"GQA ratio {gqa_rows} exceeds the AKV-v2 contract")
    if golden_shape != [head_dim * query_heads, 1, 1, 1]:
        raise SystemExit("attention output shape does not match Q topology")

    active_kv = active_mask_prefix(
        block / f"{TENSOR_STEMS['mask']}.bin", kv_capacity
    )
    attention_params_path = block / f"{ATTENTION_PARAMS_STEM}.json"
    attention_params = (
        json.loads(attention_params_path.read_text())
        if attention_params_path.is_file()
        else {}
    )
    if args.scale is not None:
        scale = args.scale
        scale_source = "command-line override"
    elif "scale" in attention_params:
        scale = float(attention_params["scale"])
        scale_source = "captured GGML attention op"
    else:
        scale = 1.0 / math.sqrt(head_dim)
        scale_source = "legacy inferred 1/sqrt(head_dim)"
    max_bias = float(attention_params.get("max_bias", 0.0))
    logit_softcap = float(attention_params.get("logit_softcap", 0.0))
    model_metadata_path = root / "model.json"
    model_metadata = (
        json.loads(model_metadata_path.read_text())
        if model_metadata_path.is_file() else {}
    )
    model = args.model or model_metadata.get("description", "unknown model")

    case_dir = root / "replay" / "cases" / "operator" / "decode" / "attention_core"
    case_dir.mkdir(parents=True, exist_ok=True)
    case = {
        "kind": "attention_core",
        **{
            role: relative_tensor_path(stem)
            for role, stem in TENSOR_STEMS.items()
        },
        "scale": scale,
        "max_bias": max_bias,
        "logit_softcap": logit_softcap,
        "v_transposed": False,
        "atol": args.atol,
        "rtol": args.rtol,
        "provenance": {
            "classification": "real model Decode activation capture",
            "model": model,
            "head_dim": head_dim,
            "query_heads": query_heads,
            "kv_heads": kv_heads,
            "gqa_rows": gqa_rows,
            "active_kv": active_kv,
            "physical_kv_capacity": kv_capacity,
            "attention_op": attention_params.get("op", "unknown"),
            "scale_source": scale_source,
        },
    }
    (case_dir / "case.json").write_text(json.dumps(case, indent=2) + "\n")

    manifest_dir = root / "replay"
    manifest = {
        "schema_version": 1,
        "model": model,
        "source": args.source,
        "classification": "real model Decode activation capture",
        "topology": case["provenance"],
        "cases": [{
            "id": "operator/decode/attention_core",
            "level": "operator-leaf",
            "kind": "attention_core",
            "path": "replay/cases/operator/decode/attention_core",
        }],
    }
    (manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        f"packaged {model}: D={head_dim} QH={query_heads} KVH={kv_heads} "
        f"GQA={gqa_rows} active_KV={active_kv}/{kv_capacity}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
