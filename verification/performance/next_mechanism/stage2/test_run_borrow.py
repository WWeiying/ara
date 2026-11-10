import unittest

from run_borrow import LOCAL, SOURCES, check_log


class BorrowHostTest(unittest.TestCase):
    text = 'STAGE2_BORROW_PASS accepted=7012 returned=7000 flushed=12 blocked=80 withdrawals=6 resets=4 latency=3\n'

    def test_complete(self):
        self.assertEqual(check_log(self.text)['latency'], 3)

    def test_failed_or_duplicate(self):
        for text in (self.text * 2, '', self.text + 'Fatal:', self.text + 'Error:'):
            with self.assertRaises(ValueError):
                check_log(text)

    def test_coverage_and_latency(self):
        for before, after in (('7012', '7013'), ('returned=7000', 'returned=6000'),
                              ('flushed=12', 'flushed=0'), ('blocked=80', 'blocked=0'),
                              ('withdrawals=6', 'withdrawals=0'), ('resets=4', 'resets=0'),
                              ('latency=3', 'latency=2')):
            with self.assertRaises(ValueError):
                check_log(self.text.replace(before, after))

    def test_no_parent_owned_files(self):
        self.assertNotIn('vmfpu_tb.sv', LOCAL)
        self.assertNotIn('run_vmfpu.py', LOCAL)
        self.assertEqual(sum(p.endswith('/simd_mul.sv') for p in SOURCES), 1)
        self.assertEqual(sum(p.endswith('/qbs_lane_mul_borrow.sv') for p in SOURCES), 1)
        self.assertFalse(any('/vmfpu.sv' in p for p in SOURCES))


if __name__ == '__main__':
    unittest.main()
