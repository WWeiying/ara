#!/usr/bin/env python3
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[2] /
                  "llama_qwen25_q8_0_prefill_m4_direct_qbs/script/gen_data.py"),
               run_name="__main__")
