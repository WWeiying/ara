#!/usr/bin/env python3
"""Whole online-schedule equivalence; host evidence is not RTL performance."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


class GroupedOnlineTest(unittest.TestCase):
    def test_schedule(self):
        for optimization, contraction in (('-O0', 'off'), ('-O3', 'off'), ('-O3', 'fast')):
            with self.subTest(optimization=optimization, contraction=contraction), tempfile.TemporaryDirectory() as temp:
                binary = Path(temp) / 'online'
                subprocess.run([
                    shutil.which('gcc'), '-std=gnu11', optimization,
                    '-Wall', '-Wextra', '-Werror', '-fno-fast-math',
                    '-ffp-contract='+contraction, '-frounding-math', '-I'+str(ROOT),
                    str(HERE/'test_online_grouped.c'), '-lm', '-o', str(binary),
                ], check=True, timeout=120)
                result = subprocess.run([str(binary)], check=True, text=True,
                                        capture_output=True, timeout=120)
                self.assertEqual(result.stdout,
                    'GROUPED_ONLINE_PASS cases=2800 injected_errors=12 exact=1 '
                    'flags=1 callbacks=1 guards=1 double_oracle=1\n')


if __name__ == '__main__':
    unittest.main()
