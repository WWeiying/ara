"""Check storage bounds from the current decoder's encoded integer ranges.

No assumption is made that an encoded Q8_K bsum equals its activation sum.
Floating scales are outside the integer correction datapath.
"""

import itertools
import unittest


# name, quant range, integer-scale range, subgroup elements, block elements
PROFILES = (
    ("Q4_K", (0, 15), (0, 63), 32, 256),
    ("Q6_K", (-32, 31), (-128, 127), 16, 256),
    ("Q4_0", (-8, 7), (1, 1), 32, 32),
    ("Q3_K", (-4, 3), (-32, 31), 16, 256),
    ("Q5_K", (0, 31), (0, 63), 32, 256),
    ("Q8_0", (-128, 127), (1, 1), 32, 32),
    ("Q2_K", (0, 3), (0, 15), 16, 256),
    ("Q5_0", (-16, 15), (1, 1), 32, 32),
    ("IQ4_NL", (-127, 113), (1, 1), 32, 32),
)


class QbsBounds(unittest.TestCase):
    def assert_signed_fits(self, values, bits):
        self.assertGreaterEqual(min(values), -(1 << (bits - 1)))
        self.assertLess(max(values), 1 << (bits - 1))

    def test_all_integer_profiles(self):
        for name, quant, scale, group, block in PROFILES:
            with self.subTest(profile=name):
                products = [q * a for q, a in itertools.product(quant, (-128, 127))]
                self.assert_signed_fits([p * group for p in products], 21)
                scaled = [q * a * s for q, a, s in
                          itertools.product(quant, (-128, 127), scale)]
                self.assert_signed_fits([p * block for p in scaled], 28)

    def test_correction_guard_bits(self):
        products = [d * s for d, s in itertools.product(
            (-(1 << 20), (1 << 20) - 1), (-128, 127))]
        self.assert_signed_fits(products, 29)
        self.assert_signed_fits([p + total for p, total in itertools.product(
            products, (-(1 << 27), (1 << 27) - 1))], 30)

    def test_noncanonical_bsum_is_not_truncated(self):
        products = [b * m for b, m in itertools.product((-32768, 32767), (0, 63))]
        self.assert_signed_fits(products, 23)
        self.assert_signed_fits([p + total for p, total in itertools.product(
            products, (-(1 << 31), (1 << 31) - 1))], 33)
        for groups, minimum_max in ((8, 63), (16, 15)):
            self.assert_signed_fits([b * minimum_max * groups
                                     for b in (-32768, 32767)], 32)


if __name__ == "__main__":
    unittest.main()
