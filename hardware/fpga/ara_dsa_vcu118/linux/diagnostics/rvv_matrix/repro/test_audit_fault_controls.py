import unittest
from audit_fault_controls import summary


class SummaryTests(unittest.TestCase):
    def test_summary(self):
        line = 'RVV_FAULT_REPLAY_FAIL sew=8 cases=48 signals=48 errors=32'
        self.assertEqual(summary(line), dict(verdict='FAIL', sew=8, cases=48, signals=48, errors=32))
        with self.assertRaises(ValueError):
            summary(line + '\n' + line)

    def test_no_terminal_summary(self):
        self.assertIsNone(summary('RVV_FAULT_BEGIN unmapped=0'))


if __name__ == '__main__':
    unittest.main()
