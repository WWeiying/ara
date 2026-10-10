import unittest
import diagnose_native_toggle_ratios763 as r


class Counts(unittest.TestCase):
    def test_actual_ratio_text_not_serialized_bits(self):
        counts=r.parse_ratio(' 65,080 / 100,000 ','65.08%')
        self.assertEqual(counts['native_numerator'],65080)
        self.assertEqual(counts['native_denominator'],100000)

    def test_percentage_only_or_invalid_counts_hold(self):
        for value in ('65.08%','65.08% (65080/100000)','100/0','101/100','NA','bits=10896'):
            with self.assertRaises(Exception):r.parse_ratio(value,'65.08%')

    def test_mismatched_native_counts_reject(self):
        with self.assertRaises(Exception):r.parse_ratio('1/2','65.08%')

    def test_fraction_rounding_boundary(self):
        self.assertEqual(r.parse_ratio('1 / 3','33.33%')['uncovered'],2)


if __name__=='__main__':unittest.main()
