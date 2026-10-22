"""Focused stimulus/oracle tests; no simulator or coverage claims."""
from fractions import Fraction
import unittest

import build_gap95_preflight as build


class Gap95Test(unittest.TestCase):
    def test_exact_inputs_outputs_and_selectors(self):
        for width, fraction_bits, bias in ((64, 52, 1023), (32, 23, 127), (16, 10, 15)):
            for k in range(64):
                bits = (bias << fraction_bits) | (k << (fraction_bits - 6))
                significand = Fraction((1 << fraction_bits) + (bits & ((1 << fraction_bits) - 1)),
                                       1 << fraction_bits)
                self.assertEqual(significand, 1 + Fraction(k, 64))
                self.assertEqual(significand / significand, 1)
                self.assertEqual(-significand / significand, -1)
                self.assertEqual(64 | ((bits >> (fraction_bits - 6)) & 63), 64 + k)

    def test_all_physical_element_positions(self):
        for width, (vl, checks) in build.CASES.items():
            repeat = 4 * (64 // width)
            seen = {(lane, sub): set() for lane in range(4) for sub in range(64 // width)}
            for batch in range(8):
                for i in range(vl):
                    lane = (i // (64 // width)) % 4
                    sub = i % (64 // width)
                    seen[lane, sub].add(batch * 8 + i // repeat)
            self.assertTrue(all(v == set(range(64)) for v in seen.values()))
            self.assertEqual(checks, 16 * (3 * vl + 5))
            self.assertEqual(16 * 3 * vl * width // 8, 12288)

    def test_c_contract_and_three_independent_cases(self):
        source = (build.APP / "gap95_divisor_bound_common.h").read_text()
        for fragment in ("vfdiv.vv v16, v8, v4", "if (flags != 0)", "if (restart != 0)",
                         "if (vl != COUNT)", "output[COUNT + 1]", "if (lhs[i] !=", "if (rhs[i] !="):
            self.assertIn(fragment, source)
        for width in build.CASES:
            self.assertIn("#define GAP95_EEW %d" % width,
                          (build.APP / ("vgap95_div%d_bound.c" % width)).read_text())


if __name__ == "__main__":
    unittest.main()
