#!/usr/bin/env python3
"""Build deduplicated real-data Prefill Attention M/P replay matrices."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path


TYPE_BYTES = {"f16": 2, "f32": 4}
TENSOR_ROLES = ("input_a", "key", "value", "mask", "golden")
QUERY_AXIS_ROLES = {"input_a", "mask", "golden"}


@dataclass(frozen=True)
class SourceSpec:
    root: Path
    case_id: str
    tokens: tuple[int, ...]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


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


def parse_source(value: str) -> SourceSpec:
    fields = value.split("::")
    if len(fields) != 3:
        raise argparse.ArgumentTypeError(
            "source must be ROOT::CASE_ID::M[,M...]"
        )
    root = Path(fields[0]).resolve()
    case_id = fields[1]
    try:
        tokens = tuple(sorted({int(token) for token in fields[2].split(",")}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("source token list must be integers") from error
    if not tokens or any(token <= 0 for token in tokens):
        raise argparse.ArgumentTypeError("source token counts must be positive")
    return SourceSpec(root, case_id, tokens)


def find_case(root: Path, case_id: str) -> tuple[Path, Path, dict]:
    manifest_path = root / "replay" / "manifest.json"
    manifest = load_json(manifest_path)
    matches = [entry for entry in manifest.get("cases", [])
               if entry.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError(
            f"{manifest_path}: expected one case {case_id}, found {len(matches)}"
        )
    case_dir = (root / matches[0]["path"]).resolve()
    case_path = case_dir / "case.json"
    return manifest_path, case_path, load_json(case_path)


def load_tensor(case_dir: Path, case: dict, role: str) -> dict:
    metadata_path = (case_dir / case[role]).resolve()
    data_path = metadata_path.with_suffix(".bin")
    metadata = load_json(metadata_path)
    tensor_type = str(metadata.get("type", "")).lower()
    shape = [int(value) for value in metadata.get("shape", [])]
    strides = [int(value) for value in metadata.get("strides", [])]
    if tensor_type not in TYPE_BYTES or len(shape) != 4:
        raise ValueError(f"unsupported tensor metadata: {metadata_path}")
    if any(value <= 0 for value in shape):
        raise ValueError(f"non-positive tensor shape: {metadata_path}")
    if strides != contiguous_strides(shape, TYPE_BYTES[tensor_type]):
        raise ValueError(f"non-contiguous tensor: {metadata_path}")
    payload = data_path.read_bytes()
    if len(payload) != int(metadata.get("nbytes", -1)):
        raise ValueError(f"tensor byte count mismatch: {data_path}")
    return {
        "metadata": metadata,
        "metadata_path": metadata_path,
        "data_path": data_path,
        "payload": payload,
    }


def causal_prefixes(mask: dict) -> list[int]:
    shape = mask["metadata"]["shape"]
    kv_capacity, query_tokens, _, _ = [int(value) for value in shape]
    values = struct.unpack(
        f"<{len(mask['payload']) // 2}H", mask["payload"]
    )
    prefixes = []
    for token in range(query_tokens):
        row = values[token * kv_capacity:(token + 1) * kv_capacity]
        prefix = 0
        while prefix < kv_capacity and row[prefix] == 0x0000:
            prefix += 1
        if prefix == 0 or any(value != 0xFC00 for value in row[prefix:]):
            raise ValueError(f"mask row {token} is not an exact causal prefix")
        prefixes.append(prefix)
    past_tokens = prefixes[0] - 1
    expected = [past_tokens + token + 1 for token in range(query_tokens)]
    if prefixes != expected:
        raise ValueError("mask prefixes do not advance by one token")
    return prefixes


def slice_axis1_prefix(tensor: dict, tokens: int) -> tuple[dict, bytes]:
    metadata = dict(tensor["metadata"])
    shape = [int(value) for value in metadata["shape"]]
    if tokens > shape[1]:
        raise ValueError(f"requested M={tokens} exceeds source M={shape[1]}")
    element_bytes = TYPE_BYTES[str(metadata["type"]).lower()]
    row_bytes = shape[0] * element_bytes
    plane_bytes = shape[1] * row_bytes
    payload = b"".join(
        tensor["payload"][plane * plane_bytes:
                          plane * plane_bytes + tokens * row_bytes]
        for plane in range(shape[2] * shape[3])
    )
    metadata["shape"] = [shape[0], tokens, shape[2], shape[3]]
    metadata["strides"] = contiguous_strides(metadata["shape"], element_bytes)
    metadata["nbytes"] = len(payload)
    return metadata, payload


def hardlink_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError as error:
        if error.errno not in {errno.EXDEV, errno.EPERM, errno.EACCES}:
            raise
        shutil.copyfile(source, destination)


def emit_tensor(case_dir: Path, role: str, tensor: dict, tokens: int) -> str:
    metadata_path = case_dir / f"{role}.json"
    data_path = case_dir / f"{role}.bin"
    if role in QUERY_AXIS_ROLES:
        metadata, payload = slice_axis1_prefix(tensor, tokens)
        write_json(metadata_path, metadata)
        data_path.write_bytes(payload)
    else:
        write_json(metadata_path, tensor["metadata"])
        hardlink_or_copy(tensor["data_path"], data_path)
    return metadata_path.name


def validate_topology(tensors: dict[str, dict]) -> dict:
    q_shape = [int(value) for value in tensors["input_a"]["metadata"]["shape"]]
    k_shape = [int(value) for value in tensors["key"]["metadata"]["shape"]]
    v_shape = [int(value) for value in tensors["value"]["metadata"]["shape"]]
    mask_shape = [int(value) for value in tensors["mask"]["metadata"]["shape"]]
    golden_shape = [int(value) for value in tensors["golden"]["metadata"]["shape"]]
    dim, source_tokens, q_heads, q_batch = q_shape
    k_dim, kv_capacity, kv_heads, kv_batch = k_shape
    if q_batch != 1 or kv_batch != 1 or k_shape != v_shape or dim != k_dim:
        raise ValueError("unsupported Q/K/V topology")
    if mask_shape != [kv_capacity, source_tokens, 1, 1]:
        raise ValueError("mask topology mismatch")
    if golden_shape != [dim * q_heads, source_tokens, 1, 1]:
        raise ValueError("golden topology mismatch")
    if q_heads % kv_heads:
        raise ValueError("invalid GQA topology")
    prefixes = causal_prefixes(tensors["mask"])
    return {
        "dim": dim,
        "source_tokens": source_tokens,
        "q_heads": q_heads,
        "kv_heads": kv_heads,
        "gqa_rows": q_heads // kv_heads,
        "kv_capacity": kv_capacity,
        "past_tokens": prefixes[0] - 1,
        "prefixes": prefixes,
    }


def build_case(spec: SourceSpec, output_root: Path, tokens: int) -> tuple[dict, dict]:
    manifest_path, source_case_path, source_case = find_case(
        spec.root, spec.case_id
    )
    source_case_dir = source_case_path.parent
    tensors = {
        role: load_tensor(source_case_dir, source_case, role)
        for role in TENSOR_ROLES
    }
    topology = validate_topology(tensors)
    if tokens > topology["source_tokens"]:
        raise ValueError(
            f"{spec.case_id}: requested M={tokens}, source M={topology['source_tokens']}"
        )
    past_tokens = topology["past_tokens"]
    output_id = f"operator/prefill/p{past_tokens}_m{tokens}/attention_core"
    case_dir = output_root / "replay" / "cases" / output_id
    if case_dir.exists():
        raise ValueError(f"duplicate matrix case: {output_id}")
    case_dir.mkdir(parents=True)

    output_case = {
        key: value for key, value in source_case.items()
        if key not in TENSOR_ROLES and key != "provenance"
    }
    for role in TENSOR_ROLES:
        output_case[role] = emit_tensor(case_dir, role, tensors[role], tokens)
    output_case["provenance"] = {
        "classification": "real llama.cpp query-token prefix",
        "source_root": str(spec.root),
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256(manifest_path),
        "source_case_id": spec.case_id,
        "source_case_sha256": sha256(source_case_path),
        "query_tokens": tokens,
        "past_tokens": past_tokens,
        "kv_payload": "unchanged from source capture",
    }
    case_path = case_dir / "case.json"
    write_json(case_path, output_case)

    prefixes = topology["prefixes"][:tokens]
    summary = {
        "case_id": output_id,
        "source_case_id": spec.case_id,
        "M_query_tokens": tokens,
        "P_past_tokens": past_tokens,
        "head_dim": topology["dim"],
        "query_heads": topology["q_heads"],
        "kv_heads": topology["kv_heads"],
        "gqa_rows": topology["gqa_rows"],
        "kv_capacity": topology["kv_capacity"],
        "active_prefix_first": prefixes[0],
        "active_prefix_last": prefixes[-1],
        "atol": output_case["atol"],
        "rtol": output_case["rtol"],
        "attention_macs": (
            2 * sum(prefixes) * topology["q_heads"] * topology["dim"]
        ),
        "case_sha256": sha256(case_path),
        "status": "PASS",
    }
    entry = {
        "id": output_id,
        "level": "operator-leaf",
        "kind": "attention_core",
        "path": os.path.relpath(case_dir, output_root),
    }
    return entry, summary


def build(output_root: Path, specs: list[SourceSpec]) -> dict:
    output_root = output_root.resolve()
    if output_root.exists():
        raise ValueError(f"output root already exists: {output_root}")
    output_root.mkdir(parents=True)
    entries = []
    cases = []
    model_hash = None
    first_model_path = None
    try:
        for spec in specs:
            source_model_path = spec.root / "model.json"
            source_model_hash = sha256(source_model_path)
            if model_hash is None:
                model_hash = source_model_hash
                first_model_path = source_model_path
            elif source_model_hash != model_hash:
                raise ValueError("matrix sources use different model metadata")
            for tokens in spec.tokens:
                entry, summary = build_case(spec, output_root, tokens)
                entries.append(entry)
                cases.append(summary)
        assert first_model_path is not None
        hardlink_or_copy(first_model_path, output_root / "model.json")
        manifest = {
            "schema_version": 1,
            "source": "real llama.cpp Prefill Attention matrix",
            "model_metadata_sha256": model_hash,
            "cases": entries,
        }
        manifest_path = output_root / "replay" / "manifest.json"
        write_json(manifest_path, manifest)
        result = {
            "schema_version": 1,
            "status": "PASS",
            "output_root": str(output_root),
            "model_metadata_sha256": model_hash,
            "manifest_sha256": sha256(manifest_path),
            "case_count": len(cases),
            "cases": cases,
        }
        write_json(output_root / "replay" / "prefill_matrix_summary.json", result)
        (output_root / "replay" / "complete").write_text(
            "PASS\n", encoding="ascii"
        )
        return result
    except Exception:
        shutil.rmtree(output_root)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_root", type=Path)
    parser.add_argument(
        "--source", action="append", required=True, type=parse_source,
        help="ROOT::CASE_ID::M[,M...] (repeatable)",
    )
    args = parser.parse_args()
    print(json.dumps(build(args.output_root, args.source), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
