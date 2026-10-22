"""Validate the source and exact-input hypothesis for a new SRT bound scan."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl'


class DivisorBoundScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pins = json.loads((ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        cls.sources = {}
        for name in ('ct_vfdsu_prepare.v', 'ct_vfdsu_srt.v',
                     'ct_vfdsu_srt_radix16_with_sqrt.v'):
            path = CORE / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != pins[str(path)]:
                raise ValueError('Frozen source drift')
            text = re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(), flags=re.S)
            cls.sources[name] = re.sub(r'\s+', '', text)

    def test_normal_divisor_alignment(self):
        text = self.sources['ct_vfdsu_prepare.v']
        for clause in ("{1'b1,ex1_oper1[51:0]}", "{1'b1,ex1_oper1[22:0],29'b0}",
                       "{1'b1,ex1_oper1[9:0],42'b0}"):
            self.assertIn(clause, text)
        self.assertIn('assignex1_divisor[52:0]=ex1_div_srt_op1[52:0];', text)
        self.assertIn('assignex1_div_srt_op1[52:0]=ex1_div_nor_srt_op1[52:0];', text)
        self.assertIn('assignex1_div_nor_srt_op1[52:0]=ex1_op1_id_nor?'
                      "{ex1_oper1_id_frac[51:0],1'b0}:ex1_div_noid_nor_srt_op1[52:0];", text)

    def test_initial_selector_and_register_capture(self):
        text = self.sources['ct_vfdsu_srt.v']
        self.assertIn("assigninitial_divisor_in[55:0]={ex1_divisor[52:0],3'b000};", text)
        self.assertIn("assigninitial_bound_sel_in[6:0]=ex1_div?initial_divisor_in[55:49]:{7{1'b0}};", text)
        self.assertIn('assigninitial_srt_en=ex1_pipedown;', text)
        inner = self.sources['ct_vfdsu_srt_radix16_with_sqrt.v']
        self.assertIn('bound_sel[6:0]<=initial_bound_sel_in[6:0];', inner)
        self.assertIn('.bound_sel(bound_sel)', inner)

    def test_all_64_selectors_and_exact_results(self):
        for fraction_bits, bias in ((52, 1023), (23, 127), (10, 15)):
            selectors = set()
            for k in range(64):
                fraction = k << (fraction_bits - 6)
                encoded = (bias << fraction_bits) | fraction
                self.assertEqual(encoded >> fraction_bits, bias)
                aligned = fraction << (52 - fraction_bits)
                selectors.add(((1 << 52) | aligned) >> 46)
                value = Fraction(1) + Fraction(fraction, 1 << fraction_bits)
                self.assertEqual(value / value, 1)
                self.assertEqual(-value / value, -1)
            self.assertEqual(selectors, set(range(0x40, 0x80)))


if __name__ == '__main__':
    unittest.main()
