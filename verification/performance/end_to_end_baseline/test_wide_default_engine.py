"""Exercise the default-path replay gates without compiling or simulating."""
from pathlib import Path
import unittest

import run_wide_default_engine as d


class DefaultEngineTests(unittest.TestCase):
    def setUp(self):
        self.vector = (d.ORIGINAL / 'matrix-base.txt').read_text()
        self.log = (d.ORIGINAL / 'run-matrix-gap0-0.log').read_text()

    def test_bound_reference(self):
        value = d.check(self.log, self.vector, self.log)
        self.assertEqual(value['normal_cases'], 36)
        self.assertTrue(value['direct_and_context_cycles_identical'])

    def test_different_arithmetic_or_missing_fault_rejected(self):
        for text in (self.log.replace('MATRIX_ENGINE_CONFIG wide=0', 'MATRIX_ENGINE_CONFIG wide=1'),
                     self.log.replace('QBS MMU atomic-fault PASS', 'missing')):
            with self.assertRaises(ValueError):
                d.check(text, self.vector, self.log)

    def test_fatal_and_duplicate_terminal_rejected(self):
        for text in (self.log + '\nFatal: unexpected\n', self.log + self.log):
            with self.assertRaises(ValueError):
                d.check(text, self.vector, self.log)

    def test_cycle_and_geometry_change_rejected(self):
        import re
        changed = re.sub(r'cycles=(\d+)', lambda m: 'cycles=' + str(int(m[1]) + 1), self.log, count=1)
        for text in (changed, self.log.replace('PASS profile=1 M=1 N=5', 'PASS profile=2 M=1 N=5', 1)):
            with self.assertRaises(ValueError):
                d.check(text, self.vector, self.log)


if __name__ == '__main__':
    unittest.main()
