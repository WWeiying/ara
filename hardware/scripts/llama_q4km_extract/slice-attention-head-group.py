#!/usr/bin/env python3

"""Derive one real Decode attention head group from a full capture."""

import argparse
import json
import shutil
from pathlib import Path


TENSOR_STEMS = {
    "query": "attn_q_input-0",
    "key": "attn_k_input-0",
    "value": "attn_v_input-0",
    "mask": "attn_mask_input-0",
    "golden": "kqv_out-0",
}

ATTENTION_PARAMS_STEM = "attention_params-0.json"

ELEMENT_BYTES = {"f16": 2, "f32": 4}


def load_tensor(block: Path, stem: str) -> tuple[dict, bytes]:
    metadata_path = block / f"{stem}.json"
    data_path = block / f"{stem}.bin"
    if not metadata_path.is_file() or not data_path.is_file():
        raise SystemExit(f"missing capture tensor pair: {stem}")
    metadata = json.loads(metadata_path.read_text())
    data = data_path.read_bytes()
    if len(data) != int(metadata["nbytes"]):
        raise SystemExit(f"size mismatch for {data_path}")
    return metadata, data


def contiguous_strides(shape: list[int], element_bytes: int) -> list[int]:
    strides = [element_bytes]
    for extent in shape[:-1]:
        strides.append(strides[-1] * extent)
    return strides


def write_tensor(
    block: Path, stem: str, metadata: dict, data: bytes, shape: list[int]
) -> None:
    element_bytes = ELEMENT_BYTES.get(metadata["type"])
    if element_bytes is None:
        raise SystemExit(f"unsupported tensor type for {stem}: {metadata['type']}")
    expected = element_bytes
    for extent in shape:
        expected *= extent
    if len(data) != expected:
        raise SystemExit(
            f"derived size mismatch for {stem}: {len(data)} != {expected}"
        )
    derived = dict(metadata)
    derived["shape"] = shape
    derived["strides"] = contiguous_strides(shape, element_bytes)
    derived["nbytes"] = len(data)
    (block / f"{stem}.json").write_text(json.dumps(derived, indent=2) + "\n")
    (block / f"{stem}.bin").write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--kv-head", type=int, default=0)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    source_block = source_root / "decode" / "block"
    if output_root.exists():
        raise SystemExit(f"output already exists: {output_root}")

    tensors = {
        role: load_tensor(source_block, stem)
        for role, stem in TENSOR_STEMS.items()
    }
    q_meta, q_data = tensors["query"]
    k_meta, k_data = tensors["key"]
    v_meta, v_data = tensors["value"]
    mask_meta, mask_data = tensors["mask"]
    golden_meta, golden_data = tensors["golden"]

    head_dim, query_tokens, query_heads, query_batches = map(
        int, q_meta["shape"]
    )
    key_dim, kv_capacity, kv_heads, key_batches = map(int, k_meta["shape"])
    if query_tokens != 1 or query_batches != 1 or key_batches != 1:
        raise SystemExit("only batch-one Decode captures are supported")
    if key_dim != head_dim or list(map(int, v_meta["shape"])) != list(
        map(int, k_meta["shape"])
    ):
        raise SystemExit("K/V topology does not match Q head dimension")
    if kv_heads <= 0 or query_heads % kv_heads != 0:
        raise SystemExit("query heads must be an integer multiple of KV heads")
    if args.kv_head < 0 or args.kv_head >= kv_heads:
        raise SystemExit(f"KV head {args.kv_head} is outside 0..{kv_heads - 1}")

    gqa_rows = query_heads // kv_heads
    first_q_head = args.kv_head * gqa_rows
    q_head_bytes = head_dim * ELEMENT_BYTES[q_meta["type"]]
    kv_head_bytes = (
        head_dim * kv_capacity * ELEMENT_BYTES[k_meta["type"]]
    )
    golden_head_bytes = head_dim * ELEMENT_BYTES[golden_meta["type"]]

    q_begin = first_q_head * q_head_bytes
    q_end = q_begin + gqa_rows * q_head_bytes
    kv_begin = args.kv_head * kv_head_bytes
    kv_end = kv_begin + kv_head_bytes
    golden_begin = first_q_head * golden_head_bytes
    golden_end = golden_begin + gqa_rows * golden_head_bytes

    output_block = output_root / "decode" / "block"
    output_block.mkdir(parents=True)
    write_tensor(
        output_block,
        TENSOR_STEMS["query"],
        q_meta,
        q_data[q_begin:q_end],
        [head_dim, 1, gqa_rows, 1],
    )
    write_tensor(
        output_block,
        TENSOR_STEMS["key"],
        k_meta,
        k_data[kv_begin:kv_end],
        [head_dim, kv_capacity, 1, 1],
    )
    write_tensor(
        output_block,
        TENSOR_STEMS["value"],
        v_meta,
        v_data[kv_begin:kv_end],
        [head_dim, kv_capacity, 1, 1],
    )
    write_tensor(
        output_block,
        TENSOR_STEMS["mask"],
        mask_meta,
        mask_data,
        list(map(int, mask_meta["shape"])),
    )
    write_tensor(
        output_block,
        TENSOR_STEMS["golden"],
        golden_meta,
        golden_data[golden_begin:golden_end],
        [head_dim * gqa_rows, 1, 1, 1],
    )

    source_model = source_root / "model.json"
    model = json.loads(source_model.read_text()) if source_model.is_file() else {}
    selection = {
        "classification": "real model Decode attention head-group slice",
        "source_root": str(source_root),
        "source_head_dim": head_dim,
        "source_query_heads": query_heads,
        "source_kv_heads": kv_heads,
        "selected_kv_head": args.kv_head,
        "selected_query_head_begin": first_q_head,
        "selected_query_heads": gqa_rows,
        "gqa_rows": gqa_rows,
        "physical_kv_capacity": kv_capacity,
    }
    model["derived_capture"] = selection
    (output_root / "model.json").write_text(json.dumps(model, indent=2) + "\n")
    (output_root / "selection.json").write_text(
        json.dumps(selection, indent=2) + "\n"
    )

    source_log = source_root / "completion.log"
    if source_log.is_file():
        shutil.copy2(source_log, output_root / "source_completion.log")
    source_attention_params = source_block / ATTENTION_PARAMS_STEM
    if source_attention_params.is_file():
        shutil.copy2(source_attention_params, output_block / ATTENTION_PARAMS_STEM)
    print(
        f"selected KV head {args.kv_head}: D={head_dim} "
        f"GQA={gqa_rows} KV={kv_capacity} from QH={query_heads}/KVH={kv_heads}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
