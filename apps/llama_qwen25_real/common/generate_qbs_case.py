#!/usr/bin/env python3
"""Materialize a real Qwen2.5 case in the QBS R4 weight layout."""

from __future__ import annotations

import contextlib
import io
import json
import runpy
from pathlib import Path


def repack_r4(source: Path, destination: Path, rows: int, k_blocks: int,
              block_bytes: int) -> None:
    raw = source.read_bytes()
    expected = rows * k_blocks * block_bytes
    if len(raw) != expected:
        raise SystemExit(
            f"QBS R4 source size mismatch: actual={len(raw)}, expected={expected}"
        )

    padded_rows = (rows + 3) & ~3
    packed = bytearray(padded_rows * k_blocks * block_bytes)
    cursor = 0
    zero_block = bytes(block_bytes)
    for row_group in range(0, padded_rows, 4):
        for block in range(k_blocks):
            for row_offset in range(4):
                row = row_group + row_offset
                if row < rows:
                    source_offset = (row * k_blocks + block) * block_bytes
                    payload = raw[source_offset:source_offset + block_bytes]
                else:
                    payload = zero_block
                packed[cursor:cursor + block_bytes] = payload
                cursor += block_bytes
    # The generic Q6_K/M1 generator may stage its row-major input and output
    # as hard links. Break that alias before replacing the output with R4 data.
    destination.unlink(missing_ok=True)
    destination.write_bytes(packed)
    if source.read_bytes() != raw:
        raise SystemExit("QBS R4 generation modified its row-major source")


def emit_blob(symbol: str, path: Path) -> None:
    print(".balign 64")
    print(f".global {symbol}_start")
    print(f".global {symbol}_end")
    print(f"{symbol}_start:")
    print(f'.incbin "{path}"')
    print(f"{symbol}_end:")


def main() -> None:
    common_dir = Path(__file__).resolve().parent
    base = runpy.run_path(str(common_dir / "generate_case.py"))

    # Reuse the existing capture validation and tensor slicing. Its x32 output
    # is immediately replaced below and is never linked into the QBS app.
    with contextlib.redirect_stdout(io.StringIO()):
        base["main"]()

    app_dir = Path.cwd()
    spec = json.loads((app_dir / "case.json").read_text(encoding="utf-8"))
    generated = app_dir / "generated"
    rows = int(spec["rows"])
    k = int(spec["k"])
    weight_type = spec["weight_type"]
    weight_format = base["WEIGHT_FORMATS"].get(weight_type)
    if weight_format is None:
        raise SystemExit(f"QBS does not support weight type {weight_type}")
    block_bytes = int(weight_format["block_bytes"])
    block_elements = int(weight_format["block_elements"])
    k_blocks = k // block_elements

    embedded_weight = generated / "embedded_weight.bin"
    repack_r4(generated / "source_weight.bin", embedded_weight, rows,
              k_blocks, block_bytes)

    provenance_path = generated / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    layout_name = "qbs_r4_block_major_v1"
    provenance["embedded_weight_layout"] = layout_name
    activation_profile = "Q8_0" if weight_type == "q8_0" else "Q8_K"
    provenance["runtime_timed_region"] = (
        f"F32_to_{activation_profile}_plus_blocking_QBS_quantized_matmul"
    )
    provenance["offline_repack_excluded"] = True
    provenance["qbs"] = {
        "descriptor_version": 1,
        "weight_layout": "W_R4_BLOCK_MAJOR",
        "activation_layout": "A_ROW_MAJOR",
        "activation_profile": activation_profile,
        "weight_profile": weight_type.upper(),
        "block_elements": block_elements,
        "tile_n": 32,
        "k_blocks": k_blocks,
    }
    provenance["tensors"]["embedded_weight.bin"] = {
        "bytes": embedded_weight.stat().st_size,
        "sha256": base["sha256"](embedded_weight),
        "layout": layout_name,
    }
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print('.section .rodata,"a",@progbits')
    emit_blob("benchmark_weight", embedded_weight.resolve())
    emit_blob("benchmark_activation",
              (generated / "activation_f32.bin").resolve())
    emit_blob("benchmark_golden", (generated / "golden_f32.bin").resolve())


if __name__ == "__main__":
    main()
