#!/usr/bin/env python3
"""Create a smaller real Prefill Attention capture by slicing query tokens."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


CASE_ID = "operator/prefill/attention_core"
CASE_RELATIVE = Path("replay/cases") / CASE_ID
TYPE_BYTES = {"f16": 2, "f32": 4}


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def contiguous_strides(shape: list[int], element_bytes: int) -> list[int]:
    strides = [element_bytes]
    for size in shape[:-1]:
        strides.append(strides[-1] * size)
    return strides


def resolve_tensor(case_dir: Path, case: dict, key: str) -> tuple[Path, dict, bytes]:
    metadata_path = (case_dir / case[key]).resolve()
    metadata = read_json(metadata_path)
    payload_path = metadata_path.with_suffix(".bin")
    payload = payload_path.read_bytes()
    shape = [int(value) for value in metadata["shape"]]
    tensor_type = metadata["type"].lower()
    if len(shape) != 4 or tensor_type not in TYPE_BYTES:
        raise ValueError(f"unsupported tensor metadata: {metadata_path}")
    expected_strides = contiguous_strides(shape, TYPE_BYTES[tensor_type])
    if [int(value) for value in metadata["strides"]] != expected_strides:
        raise ValueError(f"non-contiguous tensor is not supported: {metadata_path}")
    if len(payload) != int(metadata["nbytes"]):
        raise ValueError(f"tensor byte count mismatch: {metadata_path}")
    return metadata_path, metadata, payload


def slice_axis1_prefix(
    metadata: dict, payload: bytes, tokens: int
) -> tuple[dict, bytes]:
    shape = [int(value) for value in metadata["shape"]]
    if not 0 < tokens <= shape[1]:
        raise ValueError(f"token prefix {tokens} is outside tensor shape {shape}")
    element_bytes = TYPE_BYTES[metadata["type"].lower()]
    row_bytes = shape[0] * element_bytes
    source_plane_bytes = shape[1] * row_bytes
    chunks = []
    for plane in range(shape[2] * shape[3]):
        start = plane * source_plane_bytes
        chunks.append(payload[start : start + tokens * row_bytes])
    result = b"".join(chunks)
    sliced = dict(metadata)
    sliced["shape"] = [shape[0], tokens, shape[2], shape[3]]
    sliced["strides"] = contiguous_strides(sliced["shape"], element_bytes)
    sliced["nbytes"] = len(result)
    return sliced, result


def emit_tensor(
    output_dir: Path,
    name: str,
    metadata: dict,
    payload: bytes,
) -> str:
    metadata_name = f"{name}.json"
    metadata_path = output_dir / metadata_name
    write_json(metadata_path, metadata)
    metadata_path.with_suffix(".bin").write_bytes(payload)
    return metadata_name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tokens", type=int, required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    source_case_dir = source_root / CASE_RELATIVE
    source_case_path = source_case_dir / "case.json"
    source_case = read_json(source_case_path)
    output_case_dir = args.output_root.resolve() / CASE_RELATIVE
    if output_case_dir.exists():
        shutil.rmtree(output_case_dir)
    output_case_dir.mkdir(parents=True)

    output_case = dict(source_case)
    tensor_keys = ("input_a", "key", "value", "mask", "golden")
    for key in tensor_keys:
        metadata_path, metadata, payload = resolve_tensor(
            source_case_dir, source_case, key
        )
        if key in ("input_a", "mask", "golden"):
            metadata, payload = slice_axis1_prefix(metadata, payload, args.tokens)
        name = key
        output_case[key] = emit_tensor(output_case_dir, name, metadata, payload)
        output_case.setdefault("provenance", {})[f"source_{key}"] = str(metadata_path)

    output_case.setdefault("provenance", {}).update({
        "classification": "real-capture query-token prefix",
        "source_case": str(source_case_path),
        "query_tokens": args.tokens,
        "kv_payload": "unchanged physical K/V capacity",
    })
    write_json(output_case_dir / "case.json", output_case)

    source_manifest_path = source_root / "replay/manifest.json"
    source_manifest = read_json(source_manifest_path)
    kv_capacity = int(read_json(output_case_dir / "key.json")["shape"][1])
    manifest = {
        "schema_version": source_manifest.get("schema_version", 1),
        "model": source_manifest.get("model", "unknown"),
        "source": "query-token prefix derived from a real llama.cpp capture",
        "provenance": {
            "source_manifest": str(source_manifest_path),
            "source_manifest_sha256": sha256(source_manifest_path),
            "query_tokens": args.tokens,
        },
        "capture_shape": {
            "prefill_tokens": args.tokens,
            "kv_capacity": kv_capacity,
        },
        "cases": [{
            "id": CASE_ID,
            "level": "operator-leaf",
            "kind": "attention_core",
            "path": str(CASE_RELATIVE),
        }],
    }
    replay_dir = args.output_root.resolve() / "replay"
    write_json(replay_dir / "manifest.json", manifest)

    hashes = []
    for path in sorted(output_case_dir.iterdir()):
        if path.is_file():
            hashes.append(f"{sha256(path)}  {path.relative_to(args.output_root.resolve())}")
    (args.output_root.resolve() / "tensor.sha256").write_text(
        "\n".join(hashes) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
