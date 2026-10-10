"""Pinned source chain and exact RNE oracle for the FP32 pack scan."""
from fractions import Fraction
import json
import re
import unittest

import build_gap96_preflight as build


class PackScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((build.OUT / "repaired-aligned-build-20260930-01/build-source-pins.json").read_bytes())
        cls.sources = {}
        for name in build.SOURCE_NAMES:
            path = build.CORE / name
            if build.sha(path) != manifest[str(path)]:
                raise ValueError("Frozen source differs")
            text = re.sub(r"//[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
            cls.sources[name] = re.sub(r"\s+", "", text)

    def test_unadjusted_pack_input_and_bias_chain(self):
        prepare = self.sources["ct_vfdsu_prepare.v"]
        self.assertIn("ex1_single?{5'b0,ex1_oper0[30:23]}", prepare)
        self.assertIn("ex1_single?{5'b0,ex1_oper1[30:23]}", prepare)
        for op in (0, 1):
            self.assertIn("vfdsu_ex2_expnt_add%d[12:0]<=ex1_expnt_adder_op%d[12:0];" % (op, op), prepare)
        srt = self.sources["ct_vfdsu_srt.v"]
        self.assertIn("assignex2_expnt_result[12:0]=vfdsu_ex2_expnt_add0[12:0]-vfdsu_ex2_expnt_add1[12:0];", srt)
        self.assertIn("vfdsu_ex3_half_expnt_rst[12:0]<=vfdsu_ex2_expnt_rst[12:0];", srt)
        rounding = self.sources["ct_vfdsu_round.v"]
        self.assertIn("assignvfdsu_ex3_expnt_rst[12:0]=vfdsu_ex3_half_expnt_rst[12:0];", rounding)
        self.assertIn("vfdsu_ex3_single?13'h7f", rounding)
        self.assertIn("assignex3_expnt_adjust_result[12:0]=vfdsu_ex3_expnt_rst[12:0]+ex3_expnt_adjst[12:0];", rounding)
        self.assertIn("vfdsu_ex4_expnt_rst[12:0]<=ex3_expnt_adjust_result[12:0];", rounding)
        double = self.sources["ct_vfdsu_double.v"]
        self.assertEqual(double.count(".vfdsu_ex4_expnt_rst(vfdsu_ex4_expnt_rst)"), 2)
        pack = self.sources["ct_vfdsu_pack.v"]
        self.assertIn("case(vfdsu_ex4_expnt_rst[12:0])", pack)
        self.assertIn("assignex4_expnt_rst[12:0]=vfdsu_ex4_expnt_rst[12:0]+expnt_add_op1[12:0];", pack)

    def test_all_53_source_case_constants(self):
        block = self.sources["ct_vfdsu_pack.v"].split("case(vfdsu_ex4_expnt_rst[12:0])", 1)[1].split("endcase", 1)[0]
        constants = [int(s, 16) for s in re.findall(r"13'h([0-9a-f]+):", block)]
        self.assertEqual(constants, [(1 - n) & 8191 for n in range(53)])
        self.assertIn("default:ex4_denorm_frac[51:0]=", block)

    def test_independent_fraction_rne_oracle(self):
        unit = Fraction(1, 2 ** 149)
        for n in range(53):
            exact = Fraction(1, 2 ** 126) / (2 ** n)
            scaled = exact / unit
            lower = scaled.numerator // scaled.denominator
            remainder = scaled - lower
            rounded = lower + int(remainder > Fraction(1, 2) or
                                  (remainder == Fraction(1, 2) and lower % 2))
            self.assertEqual(rounded, 1 << (23 - n) if n <= 23 else 0)
            self.assertEqual(rounded * unit != exact, n >= 24)
            self.assertEqual(1 - (127 + n) + 127, 1 - n)
            for sign in (0, 1 << 31):
                self.assertEqual((rounded | sign) & 0x80000000, sign)

    def test_repeat_covers_shuffle_positions_and_not_gap91_duplicate(self):
        seen = {(lane, slot): set() for lane in range(4) for slot in range(2)}
        for batch in range(7):
            for i in range(64):
                n = min(batch * 8 + i // 8, 52)
                seen[i % 4, (i // 4) % 2].add(n)
        self.assertTrue(all(v == set(range(53)) for v in seen.values()))
        previous = (build.APP / "vgap91_div32_exp_lanes.c").read_text()
        self.assertIn("batch < 2", previous)
        self.assertIn("(batch * 64 + i) / 4", previous)
        self.assertEqual(14 * (3 * 64 + 5), 2758)
        self.assertEqual(14 * 3 * 64 * 4, 10752)


if __name__ == "__main__":
    unittest.main()
