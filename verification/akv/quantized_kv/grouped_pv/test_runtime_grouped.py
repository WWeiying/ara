#!/usr/bin/env python3
"""Exercise grouped runtime panel/admission/error behavior against QBS reference."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


class GroupedRuntimeTest(unittest.TestCase):
    def test_reference_and_sanitizers(self):
        for compiler, options in (('/usr/bin/gcc', []), ('/usr/bin/clang', [
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer'])):
            with self.subTest(compiler=compiler), tempfile.TemporaryDirectory() as temp:
                binary = Path(temp)/'runtime'
                sources = [HERE/'test_runtime_grouped.c',
                           ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                           ROOT/'software/akv/experimental/quantized_kv/runtime_strided.c',
                           ROOT/'software/qbs/src/qbs_runtime.c', ROOT/'verification/qbs/qbs_ref.c']
                subprocess.run([compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-fno-fast-math', '-ffp-contract=off', *options,
                    '-I'+str(ROOT), '-I'+str(ROOT/'software/qbs/include'),
                    *map(str, sources), '-lm', '-o', str(binary)], check=True, timeout=120)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertEqual(result.stdout,
                    'QUANT_STRIDED_HOST_PASS cases=288 bit_exact=1 panel_reuse=1 '
                    'bounded_copy=1 failure_no_retry=1\n')


if __name__ == '__main__':
    unittest.main()
