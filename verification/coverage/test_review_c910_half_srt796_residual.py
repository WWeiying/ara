import unittest
import review_c910_half_srt796_residual as review


class ResidualTests(unittest.TestCase):
    def test_exact_half(self):
        review.assert_wrapper('parameter FpFmtConfig=8,WIDTH=16,')

    def test_wrong_format(self):
        with self.assertRaises(ValueError):
            review.assert_wrapper('parameter FpFmtConfig=16,WIDTH=16,')

    def test_wrong_width(self):
        with self.assertRaises(ValueError):
            review.assert_wrapper('parameter FpFmtConfig=8,WIDTH=64,')

    def test_no_disabled_or_lower_lane(self):
        for slot in (0, 1, 4):
            self.assertFalse(review.focused('gen_thmulti_c910_divsqrt.gen_num_lanes[%d].active_lane.x' % slot))
        self.assertFalse(review.focused('gen_thmulti_c910_divsqrt.gen_num_lanes[2].inactive_lane.x'))

    def test_actual_frozen_and_formal_evidence(self):
        result = review.collect()
        self.assertEqual([f['net_missing'] for f in result['residual_families'].values()],
                         [13072, 6406, 3072])
        self.assertEqual(len(result['wrappers']), 8)
        self.assertEqual(len(result['existing_fp16_evidence']['matrix_writers']), 15)
        self.assertFalse(result['EDA_started'])
        self.assertFalse(result['new_EL'])
        self.assertIsNone(result['measured_increment'])


if __name__ == '__main__':
    unittest.main()
