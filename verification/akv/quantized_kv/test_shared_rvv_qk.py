#!/usr/bin/env python3
"""Executable host callback/schedule tests; no native RVV or timing claim."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class SharedRvvQkTest(unittest.TestCase):
    def compile_run(self, extra, name='gcc'):
        compiler = shutil.which(name)
        self.assertIsNotNone(compiler, name+' host compiler required')
        with tempfile.TemporaryDirectory(prefix='shared-rvv-qk-') as temp:
            binary = Path(temp) / 'test'
            build = subprocess.run([compiler, '-std=c11', '-O2', '-UNDEBUG', '-Wall',
                            '-Wextra', '-Werror', '-fno-fast-math', '-ffp-contract=off',
                            '-frounding-math', *extra, '-I'+str(ROOT),
                            str(HERE/'test_shared_rvv_qk.c'), '-lm', '-o', str(binary)],
                           capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout+build.stderr)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual(result.stdout,
                'SHARED_RVV_QK_HOST_PASS coordinates=40 schedules=576 invalid=45 '
                'nrc1=1 guards=1 exact=1 flags=1 native=0\n')
            self.assertEqual(result.stderr, '')

    def test_host_coordinates_and_both_schedules(self):
        self.compile_run([])

    def test_host_address_and_undefined_behavior(self):
        self.compile_run(['-fsanitize=address,undefined', '-fno-sanitize-recover=all'], 'clang')


if __name__ == '__main__':
    unittest.main()
