#!/usr/bin/env python3
"""Derive one real Prefill Attention GQA subgroup from a replay case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


TYPE_BYTES = {"f16": 2, "f32": 4}
TENSOR_KEYS = ("input_a", "key", "value", "mask", "golden")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contiguous_strides(shape: list[int], element_bytes: int) -> list[int]:
    strides = [element_bytes]
    for extent in shape[:-1]:
        strides.append(strides[-1] * extent)
    return strides


def load_tensor(case_dir: Path, relative_path: str) -> dict:
    metadata_path = (case_dir / relative_path).resolve()
    metadata = read_json(metadata_path)
    tensor_type = str(metadata.get("type", "")).lower()
    shape = [int(value) for value in metadata.get("shape", [])]
    if tensor_type not in TYPE_BYTES or len(shape) != 4:
        raise ValueError(f"unsupported tensor metadata: {metadata_path}")
    strides = contiguous_strides(shape, TYPE_BYTES[tensor_type])
    if [int(value) for value in metadata.get("strides", [])] != strides:
        raise ValueError(f"non-contiguous tensor: {metadata_path}")
    payload_path = metadata_path.with_suffix(".bin")
    payload = payload_path.read_bytes()
    expected = math.prod(shape) * TYPE_BYTES[tensor_type]
    if int(metadata.get("nbytes", -1)) != expected or len(payload) != expected:
        raise ValueError(f"tensor byte count mismatch: {metadata_path}")
    return {
        "metadata": metadata,
        "metadata_path": metadata_path,
        "payload": payload,
        "shape": shape,
        "type": tensor_type,
    }


def tensor_metadata(source: dict, shape: list[int], payload: bytes) -> dict:
    result = dict(source["metadata"])
    result["shape"] = shape
    result["strides"] = contiguous_strides(
        shape, TYPE_BYTES[source["type"]]
    )
    result["nbytes"] = len(payload)
    return result


def emit_tensor(case_dir: Path, key: str, source: dict,
                shape: list[int], payload: bytes) -> str:
    expected = math.prod(shape) * TYPE_BYTES[source["type"]]
    if len(payload) != expected:
        raise ValueError(f"derived {key} byte count {len(payload)} != {expected}")
    metadata_name = f"{key}.json"
    write_json(case_dir / metadata_name, tensor_metadata(source, shape, payload))
    (case_dir / f"{key}.bin").write_bytes(payload)
    return metadata_name


def causal_prefixes(mask: dict) -> list[int]:
    kv_capacity, query_tokens, _, _ = mask["shape"]
    if mask["type"] != "f16":
        raise ValueError("Prefill mask must be F16")
    values = struct.unpack(f"<{len(mask['payload']) // 2}H", mask["payload"])
    prefixes = []
    for token in range(query_tokens):
        row = values[token * kv_capacity:(token + 1) * kv_capacity]
        prefix = 0
        while prefix < kv_capacity and row[prefix] == 0x0000:
            prefix += 1
        if prefix == 0 or any(value != 0xFC00 for value in row[prefix:]):
            raise ValueError(f"mask token {token} is not a causal 0/-inf prefix")
        prefixes.append(prefix)
    expected = [prefixes[0] + token for token in range(query_tokens)]
    if prefixes != expected:
        raise ValueError(f"non-causal prefix progression: {prefixes}")
    return prefixes


def find_case(manifest: dict, case_id: str) -> dict:
    matches = [entry for entry in manifest.get("cases", [])
               if entry.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError(f"case id is not unique in source manifest: {case_id}")
    return matches[0]


def slice_capture(source_root: Path, output_root: Path, case_id: str,
                  kv_head: int, query_row_start: int,
                  query_rows: int) -> dict:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise ValueError(f"output already exists: {output_root}")

    source_manifest_path = source_root / "replay/manifest.json"
    source_manifest = read_json(source_manifest_path)
    entry = find_case(source_manifest, case_id)
    source_case_dir = (source_root / entry["path"]).resolve()
    source_case_path = source_case_dir / "case.json"
    source_case = read_json(source_case_path)
    if source_case.get("kind") != "attention_core":
        raise ValueError(f"source case is not attention_core: {source_case_path}")

    tensors = {
        key: load_tensor(source_case_dir, source_case[key])
        for key in TENSOR_KEYS
    }
    query = tensors["input_a"]
    key = tensors["key"]
    value = tensors["value"]
    mask = tensors["mask"]
    golden = tensors["golden"]
    head_dim, query_tokens, query_heads, query_batches = query["shape"]
    key_dim, kv_capacity, kv_heads, key_batches = key["shape"]
    if query["type"] != "f32" or golden["type"] != "f32":
        raise ValueError("Query and golden output must be F32")
    if key["type"] != "f16" or value["type"] != "f16":
        raise ValueError("K/V must be F16")
    if query_batches != 1 or key_batches != 1 or key_dim != head_dim:
        raise ValueError("unsupported Query/K topology")
    if value["shape"] != key["shape"]:
        raise ValueError("K/V topology mismatch")
    if mask["shape"] != [kv_capacity, query_tokens, 1, 1]:
        raise ValueError("mask topology mismatch")
    if golden["shape"] != [head_dim * query_heads, query_tokens, 1, 1]:
        raise ValueError("golden topology mismatch")
    if kv_heads <= 0 or query_heads % kv_heads:
        raise ValueError("invalid source GQA topology")

    source_gqa = query_heads // kv_heads
    if not 0 <= kv_head < kv_heads:
        raise ValueError(f"KV head {kv_head} is outside 0..{kv_heads - 1}")
    if query_rows <= 0 or query_row_start < 0 or (
            query_row_start + query_rows > source_gqa):
        raise ValueError(
            f"Query subgroup [{query_row_start}, "
            f"{query_row_start + query_rows}) exceeds source GQA {source_gqa}"
        )

    first_q_head = kv_head * source_gqa + query_row_start
    q_head_bytes = head_dim * query_tokens * TYPE_BYTES[query["type"]]
    q_begin = first_q_head * q_head_bytes
    q_payload = query["payload"][
        q_begin:q_begin + query_rows * q_head_bytes
    ]

    kv_head_bytes = head_dim * kv_capacity * TYPE_BYTES[key["type"]]
    kv_begin = kv_head * kv_head_bytes
    key_payload = key["payload"][kv_begin:kv_begin + kv_head_bytes]
    value_payload = value["payload"][kv_begin:kv_begin + kv_head_bytes]

    source_golden_token_bytes = (
        head_dim * query_heads * TYPE_BYTES[golden["type"]]
    )
    selected_golden_token_bytes = (
        head_dim * query_rows * TYPE_BYTES[golden["type"]]
    )
    golden_head_offset = (
        first_q_head * head_dim * TYPE_BYTES[golden["type"]]
    )
    golden_chunks = []
    for token in range(query_tokens):
        begin = token * source_golden_token_bytes + golden_head_offset
        golden_chunks.append(
            golden["payload"][begin:begin + selected_golden_token_bytes]
        )
    golden_payload = b"".join(golden_chunks)
    prefixes = causal_prefixes(mask)

    output_case_dir = output_root / "replay/cases" / Path(case_id)
    output_case_dir.mkdir(parents=True)
    output_case = dict(source_case)
    output_case["input_a"] = emit_tensor(
        output_case_dir, "input_a", query,
        [head_dim, query_tokens, query_rows, 1], q_payload,
    )
    output_case["key"] = emit_tensor(
        output_case_dir, "key", key,
        [head_dim, kv_capacity, 1, 1], key_payload,
    )
    output_case["value"] = emit_tensor(
        output_case_dir, "value", value,
        [head_dim, kv_capacity, 1, 1], value_payload,
    )
    output_case["mask"] = emit_tensor(
        output_case_dir, "mask", mask, mask["shape"], mask["payload"],
    )
    output_case["golden"] = emit_tensor(
        output_case_dir, "golden", golden,
        [head_dim * query_rows, query_tokens, 1, 1], golden_payload,
    )
    output_case["provenance"] = {
        **source_case.get("provenance", {}),
        "classification": "real llama.cpp Prefill Attention GQA subgroup",
        "source_root": str(source_root),
        "source_manifest": str(source_manifest_path),
        "source_manifest_sha256": sha256(source_manifest_path),
        "source_case_id": case_id,
        "source_case_sha256": sha256(source_case_path),
        "source_query_heads": query_heads,
        "source_kv_heads": kv_heads,
        "source_gqa_rows": source_gqa,
        "selected_kv_head": kv_head,
        "selected_query_row_start": query_row_start,
        "selected_query_rows": query_rows,
        "active_prefix_first": prefixes[0],
        "active_prefix_last": prefixes[-1],
    }
    write_json(output_case_dir / "case.json", output_case)

    output_manifest = {
        "schema_version": source_manifest.get("schema_version", 1),
        "model": source_manifest.get("model", "unknown"),
        "source": "GQA subgroup derived from a real llama.cpp Prefill capture",
        "provenance": output_case["provenance"],
        "topology": {
            "head_dim": head_dim,
            "query_tokens": query_tokens,
            "query_heads": query_rows,
            "kv_heads": 1,
            "gqa_rows": query_rows,
            "kv_capacity": kv_capacity,
            "active_kv": prefixes[-1],
        },
        "cases": [{
            "id": case_id,
            "level": "operator-leaf",
            "kind": "attention_core",
            "path": str(output_case_dir.relative_to(output_root)),
        }],
    }
    replay_dir = output_root / "replay"
    write_json(replay_dir / "manifest.json", output_manifest)

    hashes = []
    for path in sorted(output_case_dir.iterdir()):
        if path.is_file():
            hashes.append(f"{sha256(path)}  {path.relative_to(output_root)}")
    (output_root / "tensor.sha256").write_text(
        "\n".join(hashes) + "\n", encoding="utf-8"
    )
    return output_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--kv-head", type=int, default=0)
    parser.add_argument("--query-row-start", type=int, default=0)
    parser.add_argument("--query-rows", type=int, required=True)
    args = parser.parse_args()
    try:
        manifest = slice_capture(
            args.source_root,
            args.output_root,
            args.case_id,
            args.kv_head,
            args.query_row_start,
            args.query_rows,
        )
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
    topology = manifest["topology"]
    print(
        f"derived real Prefill slice: D={topology['head_dim']} "
        f"M={topology['query_tokens']} GQA={topology['gqa_rows']} "
        f"active_KV={topology['active_kv']}/{topology['kv_capacity']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
