#!/usr/bin/env python3
"""Reuse the Qwen capture generator while keeping this app self-contained."""

import runpy
import sys
from pathlib import Path


generator = (Path(__file__).resolve().parents[2] /
             "llama_q4km_operator" / "script" / "gen_data.py")
if not generator.is_file():
    raise SystemExit(f"missing generator: {generator}")
sys.argv[0] = str(generator)
runpy.run_path(str(generator), run_name="__main__")
