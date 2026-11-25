import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('resume', Path(__file__).with_name('gate_rvv_resume_v2.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class Tests(unittest.TestCase):
    def trace(self, wrong=False):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'commit.csv'
        with path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(('cycle', 'event', 'pc', 'port'))
            for i in range(5):
                writer.writerow((100+i, 'retire', '800022f4', 0))
                writer.writerow((100+i+int(wrong), 'retire', '800022f8', 1))
        return path

    def test_exact_pair(self):
        self.assertEqual(len(r.pairing(self.trace())), 5)

    def test_no_same_cycle_no_proof(self):
        with self.assertRaises(ValueError):
            r.pairing(self.trace(True))


if __name__ == '__main__':
    unittest.main()
