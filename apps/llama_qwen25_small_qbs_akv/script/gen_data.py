#!/usr/bin/env python3
"""Embed the real Qwen QBS and attention captures in one replay."""

import contextlib
import io
import runpy
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1]
QBS_GENERATOR = (APP.parent / "llama_qwen25_shape_decode_n32_qbs" /
                 "script" / "gen_data.py")
ATTENTION_GENERATOR = (APP.parent / "llama_q4km_operator" /
                       "script" / "gen_data.py")


def run_generator(path, arguments):
    output = io.StringIO()
    old_argv = sys.argv
    try:
        sys.argv = [str(path), *arguments]
        with contextlib.redirect_stdout(output):
            runpy.run_path(str(path), run_name="__main__")
    finally:
        sys.argv = old_argv
    return output.getvalue()


def main():
    if not QBS_GENERATOR.is_file() or not ATTENTION_GENERATOR.is_file():
        raise SystemExit("required Qwen generators are missing")
    print(run_generator(QBS_GENERATOR, []), end="")
    print(run_generator(ATTENTION_GENERATOR,
                        ["operator/decode/attention_core", "akv_v2"]),
          end="")


if __name__ == "__main__":
    main()
