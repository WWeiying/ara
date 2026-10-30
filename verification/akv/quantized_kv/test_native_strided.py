#!/usr/bin/env python3
"""Bounded K-panel wiring against QBS reference, not native RTL timing."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class StridedNativeTest(unittest.TestCase):
    def check(self, compiler, flags, omit_invalidation=False):
        with tempfile.TemporaryDirectory(prefix='quant-strided-') as directory:
            binary = Path(directory) / 'test'
            runtime = ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'
            if omit_invalidation:
                # Mechanical mutation in a temporary source, never the worker's input.
                source = runtime.read_text()
                self.assertEqual(source.count('w->panel_valid = 0;'), 1)
                mutant = Path(directory) / 'runtime_strided.c'
                mutant.write_text(source.replace('w->panel_valid = 0;', '(void)w;'))
                runtime = mutant
            subprocess.run([compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fno-fast-math', '-ffp-contract=off', *flags,
                            '-I' + str(ROOT), '-I' + str(ROOT / 'software/qbs/include'),
                            '-I' + str(ROOT / 'software/akv/experimental/quantized_kv'),
                            str(HERE / 'test_native_strided.c'),
                            str(ROOT / 'software/akv/experimental/quantized_kv/runtime.c'),
                            str(runtime),
                            str(ROOT / 'software/qbs/src/qbs_runtime.c'),
                            str(ROOT / 'verification/qbs/qbs_ref.c'), '-lm', '-o', str(binary)],
                           check=True, timeout=120)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
            if omit_invalidation:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('repeated_single_panel', result.stderr)
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('cases=288 bit_exact=1 panel_reuse=1 bounded_copy=1 failure_no_retry=1', result.stdout)
            print(result.stdout, end='')

    def test_gcc(self):
        self.check('/usr/bin/gcc', [])

    def test_sanitized(self):
        self.check('/usr/bin/clang', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])

    def test_missing_call_invalidation_is_detected(self):
        self.check('/usr/bin/gcc', [], omit_invalidation=True)


if __name__ == '__main__':
    unittest.main()
