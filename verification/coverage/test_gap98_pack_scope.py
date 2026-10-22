from fractions import Fraction
import unittest


class Pack16ScanTests(unittest.TestCase):
    def test_independent_rne_oracle_and_flags(self):
        unit = Fraction(1, 1 << 24)
        for exponent in range(5, 31):
            divisor = Fraction(2) ** (exponent - 15)
            exact = unit / divisor
            scaled = exact / unit
            lower = scaled.numerator // scaled.denominator
            remainder = scaled - lower
            rounded = lower + int(remainder > Fraction(1, 2) or
                                  (remainder == Fraction(1, 2) and lower % 2))
            self.assertEqual(rounded, 1 << (15 - exponent) if exponent <= 15 else 0)
            self.assertEqual(rounded * unit != exact, exponent >= 16)
        # Exponent31 encodes positive infinity: finite / infinity = signed zero,
        # no underflow/inexact; it is not another finite power of two.
        self.assertEqual((31 << 10) & 0x7fff, 0x7c00)

    def test_each_physical_position_has_all_exponents(self):
        seen = {(lane, slot): set() for lane in range(4) for slot in range(4)}
        for batch in range(4):
            for i in range(128):
                exponent = min(5 + batch * 8 + i // 16, 31)
                seen[i % 4, (i // 4) % 4].add(exponent)
        self.assertTrue(all(values == set(range(5, 32)) for values in seen.values()))
        self.assertEqual({-9 - e + 15 for e in range(5, 32)}, set(range(-25, 2)))
        self.assertEqual(8 * (3 * 128 + 5), 3112)
        self.assertEqual(8 * 3 * 128 * 2, 6144)


if __name__ == '__main__':
    unittest.main()
