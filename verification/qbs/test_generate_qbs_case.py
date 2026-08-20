#!/usr/bin/env python3
"""Regression test for QBS R4 generation with aliased staging files."""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "apps/llama_qwen25_real/common/generate_qbs_case.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_qbs_case", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    generator = load_generator()
    rows = 4
    k_blocks = 2
    block_bytes = 3
    source_bytes = bytes(range(rows * k_blocks * block_bytes))
    expected = bytearray()
    for block in range(k_blocks):
        for row in range(rows):
            offset = (row * k_blocks + block) * block_bytes
            expected += source_bytes[offset:offset + block_bytes]

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.bin"
        destination = Path(directory) / "embedded.bin"
        source.write_bytes(source_bytes)
        os.link(source, destination)
        generator.repack_r4(source, destination, rows, k_blocks, block_bytes)
        assert source.read_bytes() == source_bytes
        assert destination.read_bytes() == expected
        assert source.stat().st_ino != destination.stat().st_ino
    print("QBS R4 hard-link alias regression: PASS")


if __name__ == "__main__":
    main()
