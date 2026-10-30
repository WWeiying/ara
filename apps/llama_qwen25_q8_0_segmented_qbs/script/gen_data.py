#!/usr/bin/env python3
"""Use captured weights/activations and retain row-major weights for repacking."""
from pathlib import Path
import runpy

module = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                           "llama_qwen25_real/common/generate_qbs_case.py"))
module["main"]()
module["emit_blob"]("segment_source_weights",
                    (Path.cwd() / "generated/source_weight.bin").resolve())
