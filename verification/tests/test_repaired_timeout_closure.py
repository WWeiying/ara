import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(HERE))
import close_repaired_timeouts_20260930 as closure


class ClosureTests(unittest.TestCase):
    def test_budgets(self):
        self.assertEqual(closure.budget({'source_name': 'rvv:vlseg'}), 1200)
        self.assertEqual(closure.budget({'source_name': 'app:akv_portability_smoke'}), 2400)
        self.assertEqual(closure.budget({'source_name': 'app:akv_d256_reuse_smoke'}), 7200)

    def compare(self, old, new):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'old.csv', Path(d) / 'new.csv'
            a.write_text(old)
            b.write_text(new)
            return closure.prefix(a, b)

    def test_prefix_extension(self):
        self.assertEqual(self.compare('cycle,pc\n82,8000\n', 'cycle,pc\n82,8000\n84,8004\n')['status'], 'PASS')

    def test_first_divergence_retained(self):
        report = self.compare('cycle,pc\n82,8000\n84,8004\n', 'cycle,pc\n82,8000\n84,8008\n')
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['row'], 2)
        self.assertEqual(report['expected'], ['84', '8004'])
        self.assertEqual(report['actual'], ['84', '8008'])

    def test_shorter_trace_rejected(self):
        self.assertEqual(self.compare('cycle,pc\n82,8000\n', 'cycle,pc\n')['status'], 'FAIL')

    def test_incomplete_timeout_tail(self):
        self.assertTrue(self.compare('cycle,pc\n82,8000\n84', 'cycle,pc\n82,8000\n84,8004\n')['incomplete_old_tail'])


if __name__ == '__main__':
    unittest.main()
