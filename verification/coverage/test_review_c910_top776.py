import unittest
import review_c910_top776 as review


class SourceMasks(unittest.TestCase):
    def test_lfn_all_formats_and_signs(self):
        for formats in review.FORMATS.values():
            mask, ones = review.lfn_mask(formats, True)
            for fmt in formats + ['BF16_DEFAULT']:
                value, sign = review.LFN[fmt]
                self.assertEqual(value & mask, ones)
                self.assertEqual((value | (1 << sign)) & mask, ones)
                self.assertFalse(mask & (1 << sign))

    def test_reset_default_not_omitted(self):
        mask, ones = review.lfn_mask(['FP16'], True)
        self.assertFalse(mask & (1 << 7))
        self.assertEqual(review.LFN['BF16_DEFAULT'][0] & mask, ones)

    def test_disabled_format_rejected(self):
        with self.assertRaises(ValueError): review.lfn_mask(['FP8'], True)

    def test_negative_or_overwidth_word_rejected(self):
        for value in [-1, 256]:
            with self.assertRaises(ValueError): review.constant_intersection([value], 8)

    def test_coordinate_bounds_and_direction_pair(self):
        member = dict(bounds=[63, 0], serialized_offset=10)
        self.assertEqual(review.logical_bit(member, 10), 63)
        self.assertEqual(review.logical_bit(member, 11), 63)
        self.assertEqual(review.logical_bit(member, 137), 0)
        with self.assertRaises(ValueError): review.logical_bit(member, 138)

    def test_ff1_left_shift_preserves_padding(self):
        for padding in [29, 42]:
            for bit in range(padding, 52):
                value = 1 << bit
                for shift in range(52 - bit):
                    self.assertEqual((value << shift) & ((1 << padding) - 1), 0)


if __name__ == '__main__': unittest.main()
