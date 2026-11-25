import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('wide', Path(__file__).with_name('gate_rvv_wide_v1.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class Tests(unittest.TestCase):
    def trace(self, cycles):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'commit.csv'
        with path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(('cycle', 'event', 'pc'))
            writer.writerows((cycle, 'retire', '80000478') for cycle in cycles)
        return path

    def test_whole_contiguous_loops(self):
        path = self.trace([100, 8000, 16000, 20500, 29000])
        result = w.anchors_window(path, 0x80000478, 100)
        self.assertEqual((result['first_cycle'], result['last_cycle'], result['cycles']), (101, 20501, 20400))
        self.assertTrue(result['includes_compute_and_wait'])

    def test_not_enough_time(self):
        with self.assertRaises(ValueError):
            w.anchors_window(self.trace([100, 20099]), 0x80000478, 100)

    def test_oversized_loop_rejected(self):
        with self.assertRaises(ValueError):
            w.anchors_window(self.trace([100, 40000]), 0x80000478, 100)

    def test_disk_reserve(self):
        self.assertEqual(w.disk_check(448 * w.GIB, 4)['remaining_cases'], 4)
        with self.assertRaises(ValueError):
            w.disk_check(448 * w.GIB - 1, 4)


if __name__ == '__main__':
    unittest.main()
