#!/usr/bin/env python3
"""Regression tests for QBS R4 and fair standard-RVV x32 repacking."""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "apps/llama_qwen25_real/common/generate_qbs_case.py"
RVV_GENERATOR = ROOT / "apps/llama_qwen25_real/common/generate_case.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_qbs_case", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rvv_generator():
    spec = importlib.util.spec_from_file_location("generate_case", RVV_GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RVV_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_rvv_x32_roundtrip() -> None:
    generator = load_rvv_generator()
    formats = {
        "q3_K": (256, 110),
        "q4_K": (256, 144),
        "q5_K": (256, 176),
        "q6_K": (256, 210),
        "q8_0": (32, 34),
    }
    rows = 32
    blocks = 2

    for name, (block_elements, block_bytes) in formats.items():
        fields = generator.RVV_X32_FIELDS[name]
        source_bytes = bytes(
            (index * 131 + 17) & 0xff
            for index in range(rows * blocks * block_bytes)
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            packed_path = Path(directory) / "packed.bin"
            source.write_bytes(source_bytes)
            generator.repack_fields_x32(
                source,
                packed_path,
                block_elements * blocks,
                rows,
                block_elements,
                block_bytes,
                fields,
            )
            packed = memoryview(packed_path.read_bytes())

        restored = bytearray(len(source_bytes))
        cursor = 0
        for block in range(blocks):
            for offset, length, element_bytes in fields:
                for element in range(0, length, element_bytes):
                    for row in range(rows):
                        destination = (
                            (row * blocks + block) * block_bytes
                            + offset
                            + element
                        )
                        restored[destination:destination + element_bytes] = packed[
                            cursor:cursor + element_bytes
                        ]
                        cursor += element_bytes
        assert cursor == len(packed)
        assert bytes(restored) == source_bytes, f"{name} x32 roundtrip failed"


def main() -> None:
    check_rvv_x32_roundtrip()
    generator = load_generator()
    rows = 5
    k_blocks = 2
    block_bytes = 3
    source_bytes = bytes(range(rows * k_blocks * block_bytes))
    expected = bytearray()
    padded_rows = (rows + 3) & ~3
    for row_group in range(0, padded_rows, 4):
        for block in range(k_blocks):
            for row_offset in range(4):
                row = row_group + row_offset
                if row < rows:
                    offset = (row * k_blocks + block) * block_bytes
                    expected += source_bytes[offset:offset + block_bytes]
                else:
                    expected += bytes(block_bytes)

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.bin"
        destination = Path(directory) / "embedded.bin"
        source.write_bytes(source_bytes)
        os.link(source, destination)
        generator.repack_r4(source, destination, rows, k_blocks, block_bytes)
        assert source.read_bytes() == source_bytes
        assert destination.read_bytes() == expected
        assert source.stat().st_ino != destination.stat().st_ino
    print("RVV x32 and QBS R4 repacking regressions: PASS")


if __name__ == "__main__":
    main()
