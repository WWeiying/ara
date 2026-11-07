#!/usr/bin/env python3
"""Compile and run only the pure policy and host-side native API rejection checks."""
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


class TestAutoPolicy(unittest.TestCase):
    def test_policy_matrix_and_native_rejection(self):
        with tempfile.TemporaryDirectory(prefix='akv_auto_policy_') as tmp:
            binary = Path(tmp)/'policy'
            command = ['/usr/bin/gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                       '-ffunction-sections', '-fdata-sections', '-fno-fast-math', '-ffp-contract=off',
                       '-I'+str(ROOT/'software/akv/include'),
                       '-I'+str(ROOT/'software/akv/experimental/paired_heads'),
                       str(HERE/'test_auto_policy.c'),
                       *[str(ROOT/'software/akv/src'/name) for name in
                         ('akv_runtime.c', 'akv_features.c', 'akv_v2_native_riscv.c')],
                       '-Wl,--gc-sections', '-lm', '-o', str(binary)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout+compiled.stderr)
            run = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            self.assertEqual(run.stdout, 'AUTO_POLICY_HOST_PASS decisions=185760 native_execution=0\n')


if __name__ == '__main__':
    unittest.main()
