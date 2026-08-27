#!/usr/bin/env python3
"""Materialize one real Qwen2.5 operator case and emit its data.S."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path


DEFAULT_CAPTURE_ROOT = Path(
    "/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m"
)
QK_K = 256
Q4_BLOCK_BYTES = 144
Q6_BLOCK_BYTES = 210
WEIGHT_FORMATS = {
    "q3_K": {"block_elements": 256, "block_bytes": 110},
    "q4_K": {"block_elements": 256, "block_bytes": Q4_BLOCK_BYTES},
    "q5_K": {"block_elements": 256, "block_bytes": 176},
    "q6_K": {"block_elements": 256, "block_bytes": Q6_BLOCK_BYTES},
    "q8_0": {"block_elements": 32, "block_bytes": 34},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def link_or_copy(source: Path, destination: Path) -> None:
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def copy_prefix(source: Path, destination: Path, size: int) -> None:
    if source.stat().st_size == size:
        link_or_copy(source, destination)
        return
    destination.unlink(missing_ok=True)
    with source.open("rb") as source_handle, destination.open("wb") as destination_handle:
        remaining = size
        while remaining:
            chunk = source_handle.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise SystemExit(f"short source while cropping {source}")
            destination_handle.write(chunk)
            remaining -= len(chunk)


def crop_golden(
    source: Path,
    destination: Path,
    rows: int,
    inputs: int,
    capture_rows: int,
    capture_inputs: int,
) -> None:
    if rows == capture_rows and inputs == capture_inputs:
        link_or_copy(source, destination)
        return
    destination.unlink(missing_ok=True)
    source_row_bytes = capture_rows * 4
    output_row_bytes = rows * 4
    with source.open("rb") as source_handle, destination.open("wb") as destination_handle:
        for input_index in range(inputs):
            source_handle.seek(input_index * source_row_bytes)
            chunk = source_handle.read(output_row_bytes)
            if len(chunk) != output_row_bytes:
                raise SystemExit(f"short golden tensor while cropping {source}")
            destination_handle.write(chunk)


def require_tensor(path: Path, expected_bytes: int) -> dict:
    meta_path = path.with_suffix(".json")
    if not path.is_file() or not meta_path.is_file():
        raise SystemExit(f"missing captured tensor: {path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    actual = path.stat().st_size
    if actual != expected_bytes or int(meta["nbytes"]) != expected_bytes:
        raise SystemExit(
            f"size mismatch for {path}: file={actual}, metadata={meta['nbytes']}, "
            f"expected={expected_bytes}"
        )
    return meta


def require_shape(name: str, metadata: dict, expected: tuple[int, int]) -> None:
    shape = metadata.get("shape")
    if not isinstance(shape, list) or len(shape) < 2:
        raise SystemExit(f"missing shape metadata for {name}")
    actual = (int(shape[0]), int(shape[1]))
    if actual != expected:
        raise SystemExit(
            f"shape mismatch for {name}: actual={actual}, expected={expected}"
        )


def repack_fields_x32(
    source: Path,
    destination: Path,
    k: int,
    rows: int,
    block_elements: int,
    block_bytes: int,
    fields: tuple[tuple[int, int, int], ...],
) -> None:
    blocks = k // block_elements
    row_bytes = blocks * block_bytes
    raw = source.read_bytes()
    if rows % 32 != 0 or len(raw) != rows * row_bytes:
        raise SystemExit("RVV x32 repack requires complete groups of 32 rows")
    if sum(length for _, length, _ in fields) != block_bytes:
        raise SystemExit("RVV x32 field map does not cover one source block")

    packed = bytearray(len(raw))
    cursor = 0
    for row_group in range(0, rows, 32):
        for block in range(blocks):
            block_rows = [
                memoryview(raw)[
                    (row_group + row) * row_bytes + block * block_bytes:
                    (row_group + row) * row_bytes + (block + 1) * block_bytes
                ]
                for row in range(32)
            ]
            for offset, length, element_bytes in fields:
                if length % element_bytes != 0:
                    raise SystemExit("RVV x32 field has a partial element")
                for element in range(0, length, element_bytes):
                    for row in block_rows:
                        packed[cursor:cursor + element_bytes] = row[
                            offset + element:offset + element + element_bytes
                        ]
                        cursor += element_bytes
    if cursor != len(packed):
        raise SystemExit("internal RVV x32 repack size error")
    destination.write_bytes(packed)


RVV_X32_FIELDS = {
    "q3_K": ((108, 2, 2), (0, 32, 1), (32, 64, 1), (96, 12, 1)),
    "q4_K": ((0, 2, 2), (2, 2, 2), (4, 12, 1), (16, 128, 1)),
    "q5_K": ((0, 2, 2), (2, 2, 2), (4, 12, 1), (16, 32, 1),
              (48, 128, 1)),
    "q6_K": ((208, 2, 2), (192, 16, 1), (0, 128, 1), (128, 64, 1)),
    "q8_0": ((0, 2, 2), (2, 32, 1)),
}


def emit_blob(symbol: str, path: Path) -> None:
    print(".balign 64")
    print(f".global {symbol}_start")
    print(f".global {symbol}_end")
    print(f"{symbol}_start:")
    print(f'.incbin "{path}"')
    print(f"{symbol}_end:")


def main() -> None:
    app_dir = Path.cwd()
    spec = json.loads((app_dir / "case.json").read_text(encoding="utf-8"))
    capture_root = Path(os.environ.get(
        "LLAMA_CAPTURE_ROOT", spec.get("capture_root", DEFAULT_CAPTURE_ROOT)
    ))
    source_dir = capture_root / spec["phase"] / "operators" / spec["operator"]
    generated = app_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)

    k = int(spec["k"])
    rows = int(spec["rows"])
    inputs = int(spec["inputs"])
    capture_rows = int(spec.get("capture_rows", rows))
    capture_inputs = int(spec.get("capture_inputs", inputs))
    weight_type = spec["weight_type"]
    if weight_type not in WEIGHT_FORMATS:
        raise SystemExit(f"unsupported weight type: {weight_type}")
    weight_format = WEIGHT_FORMATS[weight_type]
    block_elements = int(weight_format["block_elements"])
    weight_block_bytes = int(weight_format["block_bytes"])
    if k <= 0 or k % block_elements != 0:
        raise SystemExit(
            f"K must be a positive multiple of {block_elements} for "
            f"{weight_type}: {k}"
        )
    if rows <= 0 or rows > capture_rows:
        raise SystemExit(f"invalid row slice: rows={rows}, capture_rows={capture_rows}")
    if inputs <= 0 or inputs > capture_inputs:
        raise SystemExit(
            f"invalid input slice: inputs={inputs}, capture_inputs={capture_inputs}"
        )
    use_rvv_x32 = bool(
        spec.get("rvv_x32", not spec["case_id"].endswith("_qbs"))
    )
    if use_rvv_x32 and rows % 32 != 0:
        raise SystemExit(f"{weight_type} evaluation rows must be a multiple of 32")
    weight_name = f"weight_{weight_type}.bin"
    weight_path = source_dir / weight_name
    activation_path = source_dir / "activation_f32.bin"
    golden_path = source_dir / "output_f32.bin"

    row_weight_bytes = (k // block_elements) * weight_block_bytes
    capture_weight_bytes = capture_rows * row_weight_bytes
    capture_activation_bytes = capture_inputs * k * 4
    capture_golden_bytes = capture_inputs * capture_rows * 4
    weight_bytes = rows * row_weight_bytes
    activation_bytes = inputs * k * 4
    golden_bytes = inputs * rows * 4
    metadata = {
        "weight": require_tensor(weight_path, capture_weight_bytes),
        "activation": require_tensor(activation_path, capture_activation_bytes),
        "golden": require_tensor(golden_path, capture_golden_bytes),
    }
    if metadata["weight"].get("type") != weight_type:
        raise SystemExit(
            f"weight type mismatch: metadata={metadata['weight'].get('type')}, "
            f"case={weight_type}"
        )
    require_shape("weight", metadata["weight"], (k, capture_rows))
    require_shape("activation", metadata["activation"], (k, capture_inputs))
    require_shape("golden", metadata["golden"], (capture_rows, capture_inputs))

    copy_prefix(weight_path, generated / "source_weight.bin", weight_bytes)
    copy_prefix(activation_path, generated / "activation_f32.bin", activation_bytes)
    crop_golden(
        golden_path,
        generated / "golden_f32.bin",
        rows,
        inputs,
        capture_rows,
        capture_inputs,
    )

    embedded_weight = generated / "embedded_weight.bin"
    if use_rvv_x32:
        repack_fields_x32(
            generated / "source_weight.bin",
            embedded_weight,
            k,
            rows,
            block_elements,
            weight_block_bytes,
            RVV_X32_FIELDS[weight_type],
        )
        embedded_layout = f"{weight_type}_x32_rvv"
    else:
        copy_prefix(
            generated / "source_weight.bin", embedded_weight, weight_bytes
        )
        embedded_layout = f"{weight_type}_row_major_staging"

    model_path = capture_root / "model.json"
    if not model_path.is_file():
        raise SystemExit(f"missing capture model metadata: {model_path}")
    model_metadata = json.loads(model_path.read_text(encoding="utf-8"))
    gguf_metadata = model_metadata.get("metadata", {})
    model_name = gguf_metadata.get(
        "general.name", model_metadata.get("description", spec.get("model", "unknown"))
    )
    provenance = {
        "case_id": spec["case_id"],
        "model": model_name,
        "model_description": model_metadata.get("description", model_name),
        "layer": 0,
        "phase": spec["phase"],
        "operator": spec["operator"],
        "op": "GGML_OP_MUL_MAT",
        "weight_type": weight_type,
        "activation_quantization": (
            "F32_to_Q8_0_at_runtime"
            if weight_type == "q8_0"
            else "F32_to_Q8_K_at_runtime"
        ),
        "k": k,
        "rows": rows,
        "inputs": inputs,
        "capture_rows": capture_rows,
        "capture_inputs": capture_inputs,
        "evaluation_slice": {
            "output_rows": [0, rows],
            "input_rows": [0, inputs],
        },
        "embedded_weight_layout": embedded_layout,
        "runtime_timed_region": (
            "F32_to_Q8_0_plus_quantized_matmul"
            if weight_type == "q8_0"
            else "F32_to_Q8_K_plus_quantized_matmul"
        ),
        "runtime_setup_cycles": 0,
        "offline_repack_excluded": embedded_layout.endswith("_x32_rvv"),
        "capture_root": str(capture_root),
        "capture_llama_commit": model_metadata.get("llama_commit", "unknown"),
        "model_metadata_sha256": sha256(model_path),
        "tensors": {},
        "captured_metadata": metadata,
    }
    for name in ("source_weight.bin", "activation_f32.bin", "golden_f32.bin"):
        path = generated / name
        provenance["tensors"][name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    provenance["tensors"]["embedded_weight.bin"] = {
        "bytes": embedded_weight.stat().st_size,
        "sha256": sha256(embedded_weight),
        "layout": embedded_layout,
    }
    (generated / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print('.section .rodata,"a",@progbits')
    emit_blob("benchmark_weight", embedded_weight.resolve())
    emit_blob("benchmark_activation", (generated / "activation_f32.bin").resolve())
    emit_blob("benchmark_golden", (generated / "golden_f32.bin").resolve())


if __name__ == "__main__":
    main()
