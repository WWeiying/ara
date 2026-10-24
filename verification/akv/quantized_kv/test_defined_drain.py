#!/usr/bin/env python3
"""The successor changes exactly one test-only snapshot, not computation."""
from pathlib import Path
import unittest

from build_batch_defined_drain import OLD, NEW


class DefinedDrainTest(unittest.TestCase):
    def test_exact_local_change(self):
        source = (Path(__file__).resolve().parent/'batch_qk_main.c').read_text()
        self.assertEqual(source.count(OLD), 1)
        changed = source.replace(OLD, NEW)
        self.assertEqual(changed.replace(NEW, OLD), source)
        self.assertNotIn('vmv.x.s %0,v12', changed)
        self.assertIn('vmv.x.s zero,v8', changed)
        self.assertIn('frcsr %0', changed)
        self.assertIn('csrr %1,vcsr', changed)


if __name__ == '__main__':
    unittest.main()
