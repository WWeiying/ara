#!/usr/bin/env python3

import argparse
import json
import shutil
from pathlib import Path


def load_meta(path):
    return json.loads(path.read_text())


def save_meta(path, meta):
    path.write_text(json.dumps(meta, indent=2) + "\n")


def normalize_kv(block, stem, capacity):
    meta_path = block / f"{stem}.json"
    data_path = block / f"{stem}.bin"
    meta = load_meta(meta_path)
    dim, source_capacity, heads, batches = map(int, meta["shape"])
    if meta["type"] != "f16" or batches != 1 or source_capacity < capacity:
        raise SystemExit(f"unsupported {stem} tensor: {meta}")
    source = data_path.read_bytes()
    source_head_bytes = dim * source_capacity * 2
    output_head_bytes = dim * capacity * 2
    if len(source) != source_head_bytes * heads:
        raise SystemExit(f"invalid byte size for {data_path}")
    output = b"".join(
        source[head * source_head_bytes:head * source_head_bytes + output_head_bytes]
        for head in range(heads)
    )
    data_path.write_bytes(output)
    meta["shape"] = [dim, capacity, heads, 1]
    meta["strides"] = [2, dim * 2, output_head_bytes, output_head_bytes * heads]
    meta["nbytes"] = len(output)
    save_meta(meta_path, meta)


def normalize_mask(block, capacity):
    meta_path = block / "attn_mask_input-0.json"
    data_path = block / "attn_mask_input-0.bin"
    meta = load_meta(meta_path)
    source_capacity = int(meta["shape"][0])
    if meta["type"] != "f16" or source_capacity < capacity:
        raise SystemExit(f"unsupported mask tensor: {meta}")
    output = data_path.read_bytes()[:capacity * 2]
    if len(output) != capacity * 2:
        raise SystemExit(f"invalid byte size for {data_path}")
    data_path.write_bytes(output)
    meta["shape"] = [capacity, 1, 1, 1]
    meta["strides"] = [2, capacity * 2, capacity * 2, capacity * 2]
    meta["nbytes"] = len(output)
    save_meta(meta_path, meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--capacity", type=int, default=256)
    args = parser.parse_args()
    block = args.capture_root / "decode/block"
    mask_meta = load_meta(block / "attn_mask_input-0.json")
    source_capacity = int(mask_meta["shape"][0])
    if source_capacity == args.capacity:
        return

    raw = args.capture_root / "raw_capacity_capture"
    raw.mkdir(exist_ok=False)
    for stem in ("attn_k_input-0", "attn_v_input-0", "attn_mask_input-0"):
        shutil.copy2(block / f"{stem}.bin", raw / f"{stem}.bin")
        shutil.copy2(block / f"{stem}.json", raw / f"{stem}.json")
    normalize_kv(block, "attn_k_input-0", args.capacity)
    normalize_kv(block, "attn_v_input-0", args.capacity)
    normalize_mask(block, args.capacity)
    print(f"normalized KV capacity {source_capacity} -> {args.capacity}")


if __name__ == "__main__":
    main()
