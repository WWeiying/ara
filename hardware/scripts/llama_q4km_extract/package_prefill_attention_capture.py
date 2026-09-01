#!/usr/bin/env python3
"""Validate and package every captured llama.cpp Prefill Attention chunk."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
from pathlib import Path


TENSOR_STEMS = {
    "input_a": "attn_q_input-0",
    "key": "attn_k_input-0",
    "value": "attn_v_input-0",
    "mask": "attn_mask_input-0",
    "golden": "kqv_out-0",
}
TYPE_BYTES = {"f16": 2, "f32": 4}
ATTENTION_PARAMS_STEM = "attention_params-0"
CHUNK_RE = re.compile(r"chunk-(\d+)$")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contiguous_strides(shape: list[int], element_bytes: int) -> list[int]:
    strides = [element_bytes]
    for dimension in range(3):
        strides.append(strides[-1] * shape[dimension])
    return strides


def load_tensor(block: Path, stem: str, expected_type: str) -> dict:
    metadata_path = block / f"{stem}.json"
    data_path = block / f"{stem}.bin"
    if not metadata_path.is_file() or not data_path.is_file():
        raise ValueError(f"missing capture tensor pair: {block}/{stem}")
    metadata = load_json(metadata_path)
    tensor_type = str(metadata.get("type", "")).lower()
    if tensor_type != expected_type:
        raise ValueError(
            f"{metadata_path}: expected {expected_type}, got {tensor_type}"
        )
    shape = [int(value) for value in metadata.get("shape", [])]
    strides = [int(value) for value in metadata.get("strides", [])]
    if len(shape) != 4 or any(value <= 0 for value in shape):
        raise ValueError(f"{metadata_path}: expected four positive dimensions")
    expected_strides = contiguous_strides(shape, TYPE_BYTES[tensor_type])
    if strides != expected_strides:
        raise ValueError(
            f"{metadata_path}: unsupported strides {strides}, "
            f"expected {expected_strides}"
        )
    payload = data_path.read_bytes()
    if len(payload) != int(metadata.get("nbytes", -1)):
        raise ValueError(f"{data_path}: payload size disagrees with metadata")
    if len(payload) != strides[3] * shape[3]:
        raise ValueError(f"{data_path}: payload size disagrees with shape/strides")
    return {
        "metadata_path": metadata_path,
        "data_path": data_path,
        "type": tensor_type,
        "shape": shape,
        "strides": strides,
        "nbytes": len(payload),
        "payload": payload,
    }


def causal_prefixes(mask: dict) -> list[int]:
    kv_capacity, query_tokens, _, _ = mask["shape"]
    values = struct.unpack(f"<{mask['nbytes'] // 2}H", mask["payload"])
    prefixes = []
    for token in range(query_tokens):
        row = values[token * kv_capacity : (token + 1) * kv_capacity]
        prefix = 0
        while prefix < kv_capacity and row[prefix] == 0x0000:
            prefix += 1
        if prefix == 0 or any(value != 0xFC00 for value in row[prefix:]):
            raise ValueError(
                f"mask row {token} is not an exact 0/-inf causal prefix"
            )
        prefixes.append(prefix)
    past_tokens = prefixes[0] - 1
    expected = [past_tokens + token + 1 for token in range(query_tokens)]
    if prefixes != expected:
        raise ValueError(f"non-causal prefix progression: {prefixes} != {expected}")
    return prefixes


def relative(source: Path, destination: Path) -> str:
    return os.path.relpath(source, destination)


def discover_chunks(root: Path) -> list[tuple[int, Path]]:
    chunks = []
    for directory in (root / "prefill").glob("chunk-*"):
        match = CHUNK_RE.fullmatch(directory.name)
        if match and (directory / "block").is_dir():
            chunks.append((int(match.group(1)), directory / "block"))
    chunks.sort()
    if not chunks:
        raise ValueError(f"no captured Prefill chunks below {root / 'prefill'}")
    expected = list(range(chunks[-1][0] + 1))
    observed = [index for index, _ in chunks]
    if observed != expected:
        raise ValueError(f"Prefill chunk indices are not contiguous: {observed}")
    return chunks


def analyze_chunk(root: Path, chunk_index: int, block: Path,
                  atol: float, rtol: float) -> tuple[dict, dict]:
    tensors = {
        role: load_tensor(
            block,
            stem,
            "f32" if role in {"input_a", "golden"} else "f16",
        )
        for role, stem in TENSOR_STEMS.items()
    }
    query = tensors["input_a"]
    key = tensors["key"]
    value = tensors["value"]
    mask = tensors["mask"]
    golden = tensors["golden"]
    head_dim, query_tokens, query_heads, query_batches = query["shape"]
    key_dim, kv_capacity, kv_heads, key_batches = key["shape"]
    if query_tokens <= 1 or query_batches != 1 or key_batches != 1:
        raise ValueError(f"chunk {chunk_index}: expected batch-one Prefill")
    if value["shape"] != key["shape"] or key_dim != head_dim:
        raise ValueError(f"chunk {chunk_index}: inconsistent K/V topology")
    if mask["shape"] != [kv_capacity, query_tokens, 1, 1]:
        raise ValueError(f"chunk {chunk_index}: mask topology mismatch")
    if golden["shape"] != [head_dim * query_heads, query_tokens, 1, 1]:
        raise ValueError(f"chunk {chunk_index}: output topology mismatch")
    if kv_heads <= 0 or query_heads % kv_heads:
        raise ValueError(f"chunk {chunk_index}: invalid GQA topology")
    prefixes = causal_prefixes(mask)
    past_tokens = prefixes[0] - 1

    params_path = block / f"{ATTENTION_PARAMS_STEM}.json"
    if not params_path.is_file():
        raise ValueError(f"chunk {chunk_index}: missing captured Attention parameters")
    params = load_json(params_path)
    scale = float(params.get("scale", 0.0))
    max_bias = float(params.get("max_bias", 0.0))
    logit_softcap = float(params.get("logit_softcap", 0.0))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError(f"chunk {chunk_index}: invalid Attention scale")
    if max_bias != 0.0 or logit_softcap != 0.0:
        raise ValueError(
            f"chunk {chunk_index}: max_bias/logit_softcap is outside the fast contract"
        )

    case_id = f"operator/prefill/chunk_{chunk_index}/attention_core"
    case_dir = root / "replay" / "cases" / "operator" / "prefill" / (
        f"chunk_{chunk_index}"
    ) / "attention_core"
    case_dir.mkdir(parents=True, exist_ok=True)
    case = {
        "kind": "attention_core",
        **{
            role: relative(tensor["metadata_path"], case_dir)
            for role, tensor in tensors.items()
        },
        "scale": scale,
        "max_bias": max_bias,
        "logit_softcap": logit_softcap,
        "v_transposed": False,
        "atol": atol,
        "rtol": rtol,
        "provenance": {
            "classification": "real llama.cpp Prefill Attention chunk",
            "chunk_index": chunk_index,
            "head_dim": head_dim,
            "query_tokens": query_tokens,
            "past_tokens": past_tokens,
            "query_heads": query_heads,
            "kv_heads": kv_heads,
            "gqa_rows": query_heads // kv_heads,
            "physical_kv_capacity": kv_capacity,
            "active_prefix_first": prefixes[0],
            "active_prefix_last": prefixes[-1],
            "attention_op": params.get("op", "unknown"),
        },
    }
    case_path = case_dir / "case.json"
    case_path.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    summary = {
        "case_id": case_id,
        "case_path": relative(case_path, root),
        "chunk_index": chunk_index,
        "M_query_tokens": query_tokens,
        "P_past_tokens": past_tokens,
        "head_dim": head_dim,
        "query_heads": query_heads,
        "kv_heads": kv_heads,
        "gqa_rows": query_heads // kv_heads,
        "kv_capacity": kv_capacity,
        "active_prefix_first": prefixes[0],
        "active_prefix_last": prefixes[-1],
        "query_bytes": query["nbytes"],
        "key_bytes": key["nbytes"],
        "value_bytes": value["nbytes"],
        "mask_bytes": mask["nbytes"],
        "golden_bytes": golden["nbytes"],
        "atol": atol,
        "rtol": rtol,
        "attention_macs": 2 * sum(prefixes) * query_heads * head_dim,
        "case_sha256": sha256(case_path),
        "tensor_sha256": {
            role: sha256(tensor["data_path"]) for role, tensor in tensors.items()
        },
        "status": "PASS",
    }
    manifest_entry = {
        "id": case_id,
        "level": "operator-leaf",
        "kind": "attention_core",
        "path": relative(case_dir, root),
    }
    return manifest_entry, summary


def package(root: Path, atol: float, rtol: float) -> dict:
    root = root.resolve()
    model_path = root / "model.json"
    if not model_path.is_file():
        raise ValueError(f"missing capture model metadata: {model_path}")
    entries = []
    chunks = []
    for chunk_index, block in discover_chunks(root):
        entry, summary = analyze_chunk(root, chunk_index, block, atol, rtol)
        entries.append(entry)
        chunks.append(summary)
    model = load_json(model_path)
    manifest = {
        "schema_version": 1,
        "model": model.get("description", "unknown model"),
        "source": "real host llama.cpp Prefill execution",
        "classification": "real model Prefill Attention chunk capture",
        "cases": entries,
    }
    replay = root / "replay"
    replay.mkdir(exist_ok=True)
    manifest_path = replay / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = {
        "schema_version": 1,
        "status": "PASS",
        "model": manifest["model"],
        "capture_root": str(root),
        "model_metadata_sha256": sha256(model_path),
        "manifest_sha256": sha256(manifest_path),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    (replay / "prefill_package_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (replay / "complete").write_text("PASS\n", encoding="ascii")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_root", type=Path)
    parser.add_argument("--atol", type=float, default=0.004)
    parser.add_argument("--rtol", type=float, default=0.002)
    args = parser.parse_args()
    print(json.dumps(package(args.capture_root, args.atol, args.rtol), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
