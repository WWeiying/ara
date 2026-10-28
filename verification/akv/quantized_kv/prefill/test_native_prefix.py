#!/usr/bin/env python3
"""Test the Prefill descriptor bridge; native RTL execution is a separate gate."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


class NativePrefixTest(unittest.TestCase):
    def compile_and_run(self, compiler, extra):
        with tempfile.TemporaryDirectory(prefix='native-prefix-') as directory:
            binary = Path(directory) / 'test'
            command = [compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                       '-fno-fast-math', '-ffp-contract=off', *extra,
                       '-I' + str(ROOT), '-I' + str(ROOT / 'software/qbs/include'),
                       str(HERE / 'test_native_prefix.c'),
                       str(ROOT / 'software/akv/experimental/quantized_kv/runtime.c'),
                       str(ROOT / 'software/qbs/src/qbs_runtime.c'),
                       str(ROOT / 'verification/qbs/qbs_ref.c'), '-lm', '-o', str(binary)]
            subprocess.run(command, check=True, timeout=120)
            run = subprocess.run([binary], capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout, 'NATIVE_PREFIX_PASS cases=24 alignment_copies=40 '
                             'reference=qbs_ref hardware=not_executed\n')

    def test_gcc(self):
        self.compile_and_run(shutil.which('gcc'), [])

    def test_undefined_behavior(self):
        self.compile_and_run('/usr/bin/clang', ['-fsanitize=undefined',
                                              '-fno-sanitize-recover=undefined'])


if __name__ == '__main__':
    unittest.main()
