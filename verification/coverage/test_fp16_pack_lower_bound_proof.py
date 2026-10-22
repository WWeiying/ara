import copy
import re
import unittest

from fp16_pack_lower_bound_proof import load_proof, check_sources, effective_exponent, arithmetic_proof


class FP16PackProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = {}
        cls.proof, cls.sources = load_proof(cls.pins)

    def test_exact_special_boundary_not_finite_only(self):
        self.assertEqual(effective_exponent(0x0001), -9)
        self.assertEqual(effective_exponent(0x7c00), 31)
        self.assertEqual(effective_exponent(0x0001) - effective_exponent(0x7c00) + 15, -25)
        self.assertEqual(arithmetic_proof()['lower_bound'], -25)

    def test_all_payloads_and_signs(self):
        self.assertEqual({effective_exponent(x) for x in range(65536)}, set(range(-9, 32)))

    def test_format_redirect_rejected(self):
        sources = copy.copy(self.sources)
        sources['vmfpu.sv'] += '\nassign fp_dst_fmt = fpnew_pkg::FP16ALT;\n'
        with self.assertRaises(ValueError):
            check_sources(sources)

    def test_bias_mutation_rejected(self):
        sources = copy.copy(self.sources)
        sources['ct_vfdsu_round.v'] = sources['ct_vfdsu_round.v'].replace("13'hf : 13'h7f", "13'he : 13'h7f")
        with self.assertRaises(ValueError):
            check_sources(sources)

    def test_register_hold_mutation_rejected(self):
        sources = copy.copy(self.sources)
        sources['ct_vfdsu_round.v'] = sources['ct_vfdsu_round.v'].replace(
            '<= vfdsu_ex4_expnt_rst[12:0]', "<= 13'h1fcd")
        with self.assertRaises(ValueError):
            check_sources(sources)

    def test_bfloat_alignment_mutation_rejected(self):
        sources = copy.copy(self.sources)
        sources['ct_vfdsu_srt.v'], count = re.subn(
            r'vfdsu_ex3_bfloat\s*<=\s*vfdsu_ex2_bfloat;',
            "vfdsu_ex3_bfloat <= 1'b1;", sources['ct_vfdsu_srt.v'])
        self.assertEqual(count, 1)
        with self.assertRaises(ValueError):
            check_sources(sources)

    def test_ff1_exponent_mutation_rejected(self):
        sources = copy.copy(self.sources)
        sources['ct_vfdsu_ff1.v'], count = re.subn(
            r"frac_bin_val\[12:0\]\s*=\s*13'h1ffe;",
            "frac_bin_val[12:0] = 13'h1ffd;", sources['ct_vfdsu_ff1.v'])
        self.assertEqual(count, 1)
        with self.assertRaises(ValueError):
            check_sources(sources)

    def test_round_format_bias_alignment(self):
        self.assertEqual(self.proof['ff1_half_nonzero_fraction_range'], [-9, 0])
        self.assertEqual(len(self.proof['machine_checked_alignment']), 5)


if __name__ == '__main__':
    unittest.main()
