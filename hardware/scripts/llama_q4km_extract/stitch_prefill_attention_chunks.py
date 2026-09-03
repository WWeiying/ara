#!/usr/bin/env python3
"""Stitch consecutive real llama.cpp Prefill Attention chunks."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
from pathlib import Path

import build_prefill_attention_matrix as matrix


def find_entry(root: Path, case_id: str) -> tuple[dict, Path, dict]:
    manifest = matrix.load_json(root / "replay" / "manifest.json")
    matches = [entry for entry in manifest.get("cases", []) if entry.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError(f"expected one source case {case_id}, found {len(matches)}")
    case_dir = (root / matches[0]["path"]).resolve()
    case_path = case_dir / "case.json"
    return matches[0], case_path, matrix.load_json(case_path)


def load_source(root: Path, case_id: str) -> dict:
    _entry, case_path, case = find_entry(root, case_id)
    tensors = {
        role: matrix.load_tensor(case_path.parent, case, role)
        for role in matrix.TENSOR_ROLES
    }
    topology = matrix.validate_topology(tensors)
    return {
        "case_id": case_id,
        "case_path": case_path,
        "case": case,
        "tensors": tensors,
        "topology": topology,
    }


def require_same_contract(sources: list[dict]) -> None:
    first = sources[0]
    contract_fields = (
        "kind", "scale", "max_bias", "logit_softcap", "v_transposed", "atol", "rtol"
    )
    expected_contract = {field: first["case"].get(field) for field in contract_fields}
    expected_shape = first["topology"]
    next_past = expected_shape["past_tokens"]
    for source in sources:
        topology = source["topology"]
        contract = {field: source["case"].get(field) for field in contract_fields}
        if contract != expected_contract:
            raise ValueError(f"{source['case_id']}: Attention operator contract changed")
        for field in ("dim", "q_heads", "kv_heads", "gqa_rows"):
            if topology[field] != expected_shape[field]:
                raise ValueError(f"{source['case_id']}: topology field {field} changed")
        if topology["past_tokens"] != next_past:
            raise ValueError(
                f"{source['case_id']}: expected P={next_past}, "
                f"got P={topology['past_tokens']}"
            )
        next_past += topology["source_tokens"]


def concatenate_axis1(tensors: list[dict]) -> tuple[dict, bytes]:
    first_metadata = tensors[0]["metadata"]
    tensor_type = str(first_metadata["type"]).lower()
    element_bytes = matrix.TYPE_BYTES[tensor_type]
    first_shape = [int(value) for value in first_metadata["shape"]]
    for tensor in tensors:
        metadata = tensor["metadata"]
        shape = [int(value) for value in metadata["shape"]]
        if str(metadata["type"]).lower() != tensor_type:
            raise ValueError("axis-1 tensor types differ")
        if (shape[0], shape[2], shape[3]) != (first_shape[0], first_shape[2], first_shape[3]):
            raise ValueError("axis-1 tensor non-token dimensions differ")
    row_bytes = first_shape[0] * element_bytes
    plane_count = first_shape[2] * first_shape[3]
    payload = bytearray()
    for plane in range(plane_count):
        for tensor in tensors:
            shape = [int(value) for value in tensor["metadata"]["shape"]]
            plane_bytes = shape[1] * row_bytes
            start = plane * plane_bytes
            payload.extend(tensor["payload"][start:start + plane_bytes])
    shape = list(first_shape)
    shape[1] = sum(int(tensor["metadata"]["shape"][1]) for tensor in tensors)
    metadata = dict(first_metadata)
    metadata["shape"] = shape
    metadata["strides"] = matrix.contiguous_strides(shape, element_bytes)
    metadata["nbytes"] = len(payload)
    return metadata, bytes(payload)


def concatenate_masks(sources: list[dict], target_capacity: int) -> tuple[dict, bytes]:
    payload = bytearray()
    negative_infinity = struct.pack("<H", 0xFC00)
    for source in sources:
        tensor = source["tensors"]["mask"]
        capacity, tokens, one, batch = [int(value) for value in tensor["metadata"]["shape"]]
        if one != 1 or batch != 1 or capacity > target_capacity:
            raise ValueError(f"{source['case_id']}: unsupported mask topology")
        row_bytes = capacity * 2
        padding = negative_infinity * (target_capacity - capacity)
        for token in range(tokens):
            start = token * row_bytes
            payload.extend(tensor["payload"][start:start + row_bytes])
            payload.extend(padding)
    shape = [target_capacity, sum(source["topology"]["source_tokens"] for source in sources), 1, 1]
    metadata = dict(sources[-1]["tensors"]["mask"]["metadata"])
    metadata["shape"] = shape
    metadata["strides"] = matrix.contiguous_strides(shape, 2)
    metadata["nbytes"] = len(payload)
    return metadata, bytes(payload)


def require_kv_prefix_consistency(sources: list[dict], role: str) -> None:
    final = sources[-1]["tensors"][role]
    final_shape = [int(value) for value in final["metadata"]["shape"]]
    dim, final_capacity, heads, batches = final_shape
    element_bytes = matrix.TYPE_BYTES[str(final["metadata"]["type"]).lower()]
    final_plane_bytes = dim * final_capacity * element_bytes
    for source in sources[:-1]:
        tensor = source["tensors"][role]
        shape = [int(value) for value in tensor["metadata"]["shape"]]
        if (shape[0], shape[2], shape[3]) != (dim, heads, batches):
            raise ValueError(f"{source['case_id']}: {role} topology changed")
        source_plane_bytes = dim * shape[1] * element_bytes
        for plane in range(heads * batches):
            source_start = plane * source_plane_bytes
            final_start = plane * final_plane_bytes
            if tensor["payload"][source_start:source_start + source_plane_bytes] != \
                    final["payload"][final_start:final_start + source_plane_bytes]:
                raise ValueError(
                    f"{source['case_id']}: {role} cache prefix differs from final chunk"
                )


def emit_tensor(case_dir: Path, role: str, metadata: dict, payload: bytes) -> str:
    metadata_path = case_dir / f"{role}.json"
    matrix.write_json(metadata_path, metadata)
    metadata_path.with_suffix(".bin").write_bytes(payload)
    return metadata_path.name


def stitch(source_root: Path, output_root: Path, case_ids: list[str]) -> dict:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if len(case_ids) < 2:
        raise ValueError("at least two consecutive chunks are required")
    if output_root.exists():
        raise ValueError(f"output root already exists: {output_root}")
    sources = [load_source(source_root, case_id) for case_id in case_ids]
    require_same_contract(sources)
    require_kv_prefix_consistency(sources, "key")
    require_kv_prefix_consistency(sources, "value")

    first_past = sources[0]["topology"]["past_tokens"]
    total_tokens = sum(source["topology"]["source_tokens"] for source in sources)
    target_capacity = sources[-1]["topology"]["kv_capacity"]
    if first_past + total_tokens > target_capacity:
        raise ValueError("final K/V cache does not cover every stitched Query token")
    output_id = f"operator/prefill/p{first_past}_m{total_tokens}/attention_core"
    case_dir = output_root / "replay" / "cases" / output_id
    try:
        case_dir.mkdir(parents=True)
        query_metadata, query_payload = concatenate_axis1(
            [source["tensors"]["input_a"] for source in sources]
        )
        golden_metadata, golden_payload = concatenate_axis1(
            [source["tensors"]["golden"] for source in sources]
        )
        mask_metadata, mask_payload = concatenate_masks(sources, target_capacity)
        output_case = {
            key: value for key, value in sources[0]["case"].items()
            if key not in matrix.TENSOR_ROLES and key != "provenance"
        }
        output_case["input_a"] = emit_tensor(
            case_dir, "input_a", query_metadata, query_payload
        )
        for role in ("key", "value"):
            tensor = sources[-1]["tensors"][role]
            output_case[role] = emit_tensor(
                case_dir, role, tensor["metadata"], tensor["payload"]
            )
        output_case["mask"] = emit_tensor(case_dir, "mask", mask_metadata, mask_payload)
        output_case["golden"] = emit_tensor(
            case_dir, "golden", golden_metadata, golden_payload
        )
        output_case["provenance"] = {
            "classification": "stitched consecutive real llama.cpp Prefill chunks",
            "source_root": str(source_root),
            "source_manifest_sha256": matrix.sha256(
                source_root / "replay" / "manifest.json"
            ),
            "source_case_ids": case_ids,
            "source_case_sha256": [
                matrix.sha256(source["case_path"]) for source in sources
            ],
            "query_tokens": total_tokens,
            "past_tokens": first_past,
            "kv_payload": "final real chunk after bit-exact prefix checks",
        }
        case_path = case_dir / "case.json"
        matrix.write_json(case_path, output_case)
        model_path = source_root / "model.json"
        matrix.hardlink_or_copy(model_path, output_root / "model.json")
        manifest = {
            "schema_version": 1,
            "source": "stitched consecutive real llama.cpp Prefill chunks",
            "model_metadata_sha256": matrix.sha256(model_path),
            "cases": [{
                "id": output_id,
                "level": "operator-leaf",
                "kind": "attention_core",
                "path": os.path.relpath(case_dir, output_root),
            }],
        }
        manifest_path = output_root / "replay" / "manifest.json"
        matrix.write_json(manifest_path, manifest)
        result = {
            "schema_version": 1,
            "status": "PASS",
            "case_id": output_id,
            "source_case_ids": case_ids,
            "M_query_tokens": total_tokens,
            "P_past_tokens": first_past,
            "head_dim": sources[0]["topology"]["dim"],
            "query_heads": sources[0]["topology"]["q_heads"],
            "kv_heads": sources[0]["topology"]["kv_heads"],
            "gqa_rows": sources[0]["topology"]["gqa_rows"],
            "kv_capacity": target_capacity,
            "attention_macs": 2 * sum(range(
                first_past + 1, first_past + total_tokens + 1
            )) * sources[0]["topology"]["q_heads"] * sources[0]["topology"]["dim"],
            "case_sha256": matrix.sha256(case_path),
            "manifest_sha256": matrix.sha256(manifest_path),
        }
        matrix.write_json(output_root / "replay" / "stitch_summary.json", result)
        (output_root / "replay" / "complete").write_text("PASS\n", encoding="ascii")
        return result
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("case_id", nargs="+")
    args = parser.parse_args()
    print(json.dumps(stitch(args.source_root, args.output_root, args.case_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
