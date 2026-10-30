#!/usr/bin/env python3
"""Host-only metadata/fallback admission; no native or model speedup claim."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class SelectionTest(unittest.TestCase):
    def check_binary(self, extra_flags, compiler=None):
        with tempfile.TemporaryDirectory(prefix='akv-quant-selection-') as tmp:
            binary = Path(tmp)/'test'
            subprocess.run([compiler or shutil.which('gcc'), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-frounding-math', *extra_flags, '-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'), HERE/'test_selection.c',
                ROOT/'software/qbs/src/qbs_runtime.c', '-lm', '-o', binary], check=True, timeout=120)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertRegex(result.stdout,
                r'^QUANT_SELECTION_HOST_PASS accepted=8195 rejected=65 view_cases=32768 output_untouched=1 hidden_rows_skipped=1 snan_no_invalid=1\n$')
            print(result.stdout, end='')

    def test_shapes_layouts_and_fallbacks(self):
        self.check_binary([])

    def test_sanitized_admission(self):
        # System GCC's sanitizer linker stub points to an absent libasan.so.6.
        # Use the installed host Clang/compiler-rt, never the ZCC toolchain.
        self.check_binary(['-fsanitize=address,undefined', '-fno-omit-frame-pointer'], '/usr/bin/clang')

    def test_cpp_backend_header(self):
        subprocess.run([shutil.which('g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-I'+str(ROOT), '-I'+str(ROOT/'software/qbs/include'), '-fsyntax-only', '-x', 'c++', '-'],
            input='#include "software/akv/experimental/quantized_kv/selection.h"\nint main() { return 0; }\n',
            text=True, check=True, timeout=120)


if __name__ == '__main__':
    unittest.main()
