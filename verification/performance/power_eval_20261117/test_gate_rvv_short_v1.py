import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('short', Path(__file__).with_name('gate_rvv_short_v1.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class Tests(unittest.TestCase):
    def trace(self, rows):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        p = Path(folder.name) / 'commit.csv'
        with p.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(('cycle', 'event', 'pc', 'insn'))
            writer.writerows(rows)
        return p

    def test_compute_not_uart(self):
        p = self.trace([(1, 'retire', '80000000', '57'), (2, 'uop_alloc', '0', '57'),
                        (100, 'retire', '80001000', '13'), (120, 'uop_alloc', '0', '57'),
                        (130, 'retire', '80001020', '57')])
        w = s.short_window(p, 0x80001000)
        self.assertEqual((w['first_cycle'], w['last_cycle']), (121, 1145))
        self.assertEqual(w['anchor_pc'], '0x80001020')

    def test_missing_vector_rejected(self):
        p = self.trace([(100, 'retire', '80001000', '13')])
        with self.assertRaises(ValueError):
            s.short_window(p, 0x80001000)

    def test_missing_kernel_rejected(self):
        p = self.trace([(2, 'uop_alloc', '0', '57'), (3, 'retire', '80001020', '57')])
        with self.assertRaises(ValueError):
            s.short_window(p, 0x80001000)


if __name__ == '__main__':
    unittest.main()
