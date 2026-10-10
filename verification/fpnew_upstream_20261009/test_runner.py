import csv
import io
import unittest

import oracle
import run


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.sf = oracle.SoftFloat()

    def test_i2f_overflow_not_invalid(self):
        self.assertEqual(self.sf.evaluate('i2f', 32, 16, 0, 65536), (0x7c00, 5))
        for rm, expected in ((1, 0x7bff), (2, 0x7bff), (3, 0x7c00), (4, 0x7c00)):
            self.assertEqual(self.sf.evaluate('i2f', 32, 16, rm, 65536), (expected, 5))

    def test_after_rounding_boundary(self):
        self.assertEqual(self.sf.evaluate('cast', 64, 32, 0, 0x380fffffe0000000),
                         (0x00800000, 3))
        self.assertEqual(self.sf.evaluate('cast', 64, 32, 0, 0x3810000000000000),
                         (0x00800000, 0))

    def test_real_spike_int8_saturation(self):
        for bits, unsigned, value, flags in [(0x5800, False, 0x7f, 16),
                (0xd808, False, 0x80, 16), (0xd800, False, 0x80, 0),
                (0xdbfc, True, 0, 16), (0x5c00, True, 0xff, 16),
                (0x8000, True, 0, 0)]:
            self.assertEqual(self.sf.evaluate('f2i', 16, 8, 0, bits, unsigned=unsigned),
                             (value, flags))

    def test_unsigned_not_signed_interpretation(self):
        self.assertEqual(self.sf.evaluate('i2f', 32, 64, 0, 0xffffffff, unsigned=True),
                         (0x41efffffffe00000, 0))

    def test_flush_recovery_math(self):
        self.assertEqual(self.sf.evaluate('div', 64, 64, 0, 0x4022000000000000,
                                         0x4008000000000000), (0x4008000000000000, 0))

    def test_fma_nonzero_addend_cancellation(self):
        for rm in range(5):
            self.assertEqual(self.sf.evaluate('fma', 16, 16, rm, 0x3c00, 0x3c00, 0xbc00),
                             (0x8000 if rm == 2 else 0, 0))

    def test_fma_unbounded_rounding_mode_discriminator(self):
        # Both return min-normal; only nearest retains tiny unbounded exponent.
        self.assertEqual(self.sf.evaluate('fma', 16, 16, 0, 0x300, 0x3bff, 0x100),
                         (0x400, 3))
        self.assertEqual(self.sf.evaluate('fma', 16, 16, 3, 0x300, 0x3bff, 0x100),
                         (0x400, 1))

    def test_unsigned_rows_present(self):
        rows = oracle.cases()
        actual = {(r['src'], r['dst'], r['rm']) for r in rows if r['unsigned'] and r['op'] == 'i2f'}
        self.assertEqual(actual, {(s, d, r) for s in (32, 64) for d in (16, 32, 64) for r in range(5)})


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(id=0, unit=0, expected=0x7c00, mask=0xffff, flags=5)]
        self.trace = 'id,unit,result,flags,tag,wait_cycles,mismatch\n0,0,ffffffffffff7c00,05,0,2,0\n'
        self.log = 'COMPLETE cases=1 bad=0\n'

    def test_pass(self):
        self.assertEqual(run.audit(self.rows, self.trace, self.log, False), [])

    def test_original_i2f_failure_rejected(self):
        text = self.trace.replace(',05,0,2,0', ',11,0,2,1')
        self.assertEqual(len(run.audit(self.rows, text, self.log, False)), 1)

    def test_false_pass_bit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'checker disagree'):
            run.audit(self.rows, self.trace.replace(',05,', ',11,'), self.log, False)

    def test_missing_trace_rejected(self):
        with self.assertRaisesRegex(ValueError, 'trace count'):
            run.audit(self.rows, self.trace.splitlines()[0], self.log, False)

    def test_wrong_id_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ID/unit/tag'):
            run.audit(self.rows, self.trace.replace('\n0,0,', '\n1,0,'), self.log, False)

    def test_wrong_tag_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ID/unit/tag'):
            run.audit(self.rows, self.trace.replace(',05,0,', ',05,9,'), self.log, False)

    def test_no_finish_rejected(self):
        with self.assertRaisesRegex(ValueError, 'complete marker'):
            run.audit(self.rows, self.trace, '', False)

    def test_fatal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'diagnostic'):
            run.audit(self.rows, self.trace, self.log+'Fatal: wrong\n', False)

    def test_result_corruption_rejected(self):
        text = self.trace.replace('ffff7c00,05,0,2,0', 'ffff7c01,05,0,2,1')
        self.assertEqual(len(run.audit(self.rows, text, self.log, False)), 1)

    def test_each_flag_is_checked(self):
        for bit in range(5):
            text = self.trace.replace(',05,0,2,0', f',{5 ^ (1 << bit):02x},0,2,1')
            self.assertEqual(len(run.audit(self.rows, text, self.log, False)), 1)

    def test_duplicate_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, 'trace count'):
            run.audit(self.rows, self.trace+self.trace.splitlines()[1]+'\n', self.log, False)

    def test_unknown_result_rejected(self):
        with self.assertRaises(ValueError):
            run.audit(self.rows, self.trace.replace('ffffffffffff7c00', 'xxxxxxxxxxxxxxxx'), self.log, False)


if __name__ == '__main__':
    unittest.main()
