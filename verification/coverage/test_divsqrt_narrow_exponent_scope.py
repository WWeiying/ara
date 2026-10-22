"""Conservative narrow exponent proof; not native exclusion approval."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'


class NarrowExponentScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pins = json.loads((ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        cls.sources = {}
        for name in ('ct_vfdsu_prepare.v', 'ct_vfdsu_srt.v', 'ct_vfdsu_round.v', 'ct_vfdsu_ff1.v'):
            path = ROOT / CORE / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != pins[str(path)]:
                raise ValueError('Frozen source drift: ' + name)
            cls.sources[name] = path.read_text()

    def test_narrow_exponent_fields_and_sqrt_bias(self):
        text = self.sources['ct_vfdsu_prepare.v']
        for operand in (0, 1):
            self.assertIn("{5'b0,ex1_oper%d[30:23]}" % operand, text)
            self.assertIn("{8'b0,ex1_oper%d[14:10]}" % operand, text)
            self.assertIn("{5'b0,ex1_oper%d[14:7]}" % operand, text)
        for bias in ("{6'b0,{7{1'b1}}}", "{9'b0,{4{1'b1}}}"):
            self.assertIn(bias, text)
        for operand in (0, 1):
            assignments = re.findall(r'\bvfdsu_ex2_expnt_add%d\[12:0\]\s*<=\s*([^;]+);' % operand, text)
            self.assertEqual([v.strip() for v in assignments],
                             ["13'b0", 'ex1_expnt_adder_op%d[12:0]' % operand,
                              'vfdsu_ex2_expnt_add%d[12:0]' % operand])

    def test_ff1_all_possible_two_state_outputs_are_bounded(self):
        text = self.sources['ct_vfdsu_ff1.v']
        # Require all 53 normal case arms and inspect their assigned constants.
        arms = re.findall(r"52'b([01?]{52})\s*:", text)
        self.assertEqual(len(arms), 53)
        values = re.findall(r"frac_bin_val\[12:0\]\s*=\s*13'h([0-9a-fA-F]+)", text)
        signed = {int(v, 16) - 8192 if int(v, 16) & 4096 else int(v, 16) for v in values}
        self.assertEqual(signed, set(range(-52, 1)))

    def test_difference_shift_and_registered_copy(self):
        text = re.sub(r'\s+', ' ', self.sources['ct_vfdsu_srt.v'])
        self.assertIn('ex2_expnt_result[12:0] = vfdsu_ex2_expnt_add0[12:0] - vfdsu_ex2_expnt_add1[12:0];', text)
        self.assertIn('ex2_sqrt_expnt_result[12:0] = {ex2_expnt_result[12], ex2_expnt_result[12:1]};', text)
        assignments = re.findall(r'\bvfdsu_ex3_doub_expnt_rst\[12:0\]\s*<=\s*([^;]+);', text)
        self.assertEqual(assignments, ["13'b0", 'vfdsu_ex2_expnt_rst[12:0]',
                                       'vfdsu_ex3_doub_expnt_rst[12:0]'])

    def test_explicit_double_table_constants_outside_conservative_range(self):
        targets = None
        for name, signal in (('ct_vfdsu_srt.v', 'vfdsu_ex2_expnt_rst'),
                             ('ct_vfdsu_round.v', 'vfdsu_ex3_doub_expnt_rst')):
            text = self.sources[name].split('case(%s[12:0])' % signal, 1)[1].split('endcase', 1)[0]
            values = {int(v, 16) - 8192 for v in re.findall(r"13'h([0-9a-fA-F]+)\s*:", text)}
            self.assertEqual(values, set(range(-1074, -1021)))
            targets = values
        # Overapproximate all fields, NaN/Inf encodings and normalizer outputs.
        # No 13-bit wrap is possible within this difference interval.
        for a in range(-52, 256):
            for b in range(-52, 256):
                difference = a - b
                self.assertNotIn(difference, targets)
                self.assertNotIn(difference >> 1, targets)
        self.assertNotIn(0, targets)  # Register reset must remain protected.


if __name__ == '__main__':
    unittest.main()
