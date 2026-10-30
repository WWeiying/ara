"""Test Prefill metadata mapping against actual GGML headers, without execution."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
GGML = Path('/home/wangwy/llama/llama.cpp/ggml/include')


class MapTest(unittest.TestCase):
    def run_compiler(self, compiler, flags):
        with tempfile.TemporaryDirectory(prefix='prefill-ggml-map-') as tmp:
            binary = Path(tmp) / 'test'
            subprocess.run([compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                            *flags, '-I'+str(ROOT), '-I'+str(GGML),
                            '-I'+str(ROOT/'software/qbs/include'),
                            HERE/'test_ggml_map.c', '-o', binary], check=True, timeout=120)
            run = subprocess.run([binary], capture_output=True, text=True, timeout=30, check=True)
            self.assertEqual(run.stdout, 'PREFILL_GGML_MAP_PASS accepted=20 rejected=16 '
                             'metadata_unchanged=1 execution=0\n')

    def test_gcc(self):
        self.run_compiler('/usr/bin/gcc', [])

    def test_ubsan(self):
        self.run_compiler('/usr/bin/clang', ['-fsanitize=undefined', '-fno-sanitize-recover=undefined'])

    def test_cpp_header(self):
        subprocess.run(['/usr/bin/g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT), '-I'+str(GGML), '-I'+str(ROOT/'software/qbs/include'),
                        '-x', 'c++', '-fsyntax-only', '-'],
                       input='#include "verification/akv/quantized_kv/prefill/ggml_map.h"\n',
                       text=True, check=True, timeout=120)


if __name__ == '__main__':
    unittest.main()
