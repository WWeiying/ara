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


def repack_q4_x32(source: Path, destination: Path, k: int, rows: int) -> None:
    blocks = k // QK_K
    row_bytes = blocks * Q4_BLOCK_BYTES
    raw = source.read_bytes()
    if rows % 32 != 0 or len(raw) != rows * row_bytes:
        raise SystemExit("Q4_K x32 repack requires complete groups of 32 rows")

    packed = bytearray(len(raw))
    cursor = 0
    for row_group in range(0, rows, 32):
        for block in range(blocks):
            block_rows = [
                memoryview(raw)[
                    (row_group + row) * row_bytes + block * Q4_BLOCK_BYTES:
                    (row_group + row) * row_bytes + (block + 1) * Q4_BLOCK_BYTES
                ]
                for row in range(32)
            ]
            for offset in (0, 2):
                for row in block_rows:
                    packed[cursor:cursor + 2] = row[offset:offset + 2]
                    cursor += 2
            for offset, length in ((4, 12), (16, 128)):
                for byte in range(length):
                    for row in block_rows:
                        packed[cursor] = row[offset + byte]
                        cursor += 1
    if cursor != len(packed):
        raise SystemExit("internal Q4_K repack size error")
    destination.write_bytes(packed)


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
    capture_root = Path(os.environ.get("LLAMA_CAPTURE_ROOT", DEFAULT_CAPTURE_ROOT))
    source_dir = capture_root / spec["phase"] / "operators" / spec["operator"]
    generated = app_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)

    k = int(spec["k"])
    rows = int(spec["rows"])
    inputs = int(spec["inputs"])
    capture_rows = int(spec.get("capture_rows", rows))
    capture_inputs = int(spec.get("capture_inputs", inputs))
    weight_type = spec["weight_type"]
    if k <= 0 or k % QK_K != 0:
        raise SystemExit(f"K must be a positive multiple of {QK_K}: {k}")
    if rows <= 0 or rows > capture_rows:
        raise SystemExit(f"invalid row slice: rows={rows}, capture_rows={capture_rows}")
    if inputs <= 0 or inputs > capture_inputs:
        raise SystemExit(
            f"invalid input slice: inputs={inputs}, capture_inputs={capture_inputs}"
        )
    if weight_type == "q4_K" and rows % 32 != 0:
        raise SystemExit("Q4_K evaluation rows must be a multiple of 32")
    weight_name = f"weight_{weight_type}.bin"
    weight_path = source_dir / weight_name
    activation_path = source_dir / "activation_f32.bin"
    golden_path = source_dir / "output_f32.bin"

    weight_block_bytes = 144 if weight_type == "q4_K" else 210
    row_weight_bytes = (k // QK_K) * weight_block_bytes
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
    if weight_type == "q4_K":
        repack_q4_x32(generated / "source_weight.bin", embedded_weight, k, rows)
        embedded_layout = "q4_K_x32_ara"
    else:
        link_or_copy(generated / "source_weight.bin", embedded_weight)
        embedded_layout = "gguf_row_major"

    model_path = capture_root / "model.json"
    provenance = {
        "case_id": spec["case_id"],
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",
        "layer": 0,
        "phase": spec["phase"],
        "operator": spec["operator"],
        "op": "GGML_OP_MUL_MAT",
        "weight_type": weight_type,
        "activation_quantization": "F32_to_Q8_K_at_runtime",
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
        "runtime_timed_region": "F32_to_Q8_K_plus_quantized_matmul",
        "runtime_setup_cycles": 0,
        "offline_repack_excluded": weight_type == "q4_K",
        "capture_root": str(capture_root),
        "capture_llama_commit": "316e72d38da2bf9af84f946fb6e99419d80849f9",
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
