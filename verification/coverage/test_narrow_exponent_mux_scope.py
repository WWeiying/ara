"""Additional frozen-source mux checks; not native waiver approval."""
import re
import unittest

from test_divsqrt_narrow_exponent_scope import NarrowExponentScopeTests


def compact(text):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)


def assignment(text, signal):
    matches = re.findall(r'\bassign\s+' + re.escape(signal) +
                         r'\[12:0\]\s*=\s*([^;]+);', text)
    if len(matches) != 1:
        raise ValueError('Missing or multiple drivers: ' + signal)
    return compact(matches[0])


class NarrowExponentMuxScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        NarrowExponentScopeTests.setUpClass()
        cls.sources = NarrowExponentScopeTests.sources

    def test_prepare_raw_and_normalized_muxes(self):
        text = self.sources['ct_vfdsu_prepare.v']
        for op in (0, 1):
            expected = (f"ex1_double?{{2'b0,ex1_oper{op}[62:52]}}:"
                        f"ex1_single?{{5'b0,ex1_oper{op}[30:23]}}:"
                        f"ex1_half?{{8'b0,ex1_oper{op}[14:10]}}:"
                        f"{{5'b0,ex1_oper{op}[14:7]}}")
            self.assertEqual(assignment(text, f'ex1_div_op{op}_expnt'), expected)
        self.assertEqual(assignment(text, 'ex1_expnt_adder_op0'),
                         'ex1_op0_id_nor?ex1_oper0_id_expnt[12:0]:ex1_div_op0_expnt[12:0]')
        self.assertEqual(assignment(text, 'ex1_sqrt_op1_expnt'),
                         "ex1_double?{3'b0,{10{1'b1}}}:ex1_single?{6'b0,{7{1'b1}}}:"
                         "ex1_half?{9'b0,{4{1'b1}}}:{6'b0,{7{1'b1}}}")
        block = text.split('case({ex1_div,ex1_sqrt})', 1)[1].split('endcase', 1)[0]
        self.assertEqual(compact(block),
                         "2'b10:ex1_expnt_adder_op1[12:0]=ex1_op1_id_nor?"
                         "ex1_oper1_id_expnt[12:0]:ex1_div_op1_expnt[12:0];"
                         "2'b01:ex1_expnt_adder_op1[12:0]=ex1_sqrt_op1_expnt[12:0];"
                         "default:ex1_expnt_adder_op1[12:0]=13'b0;")

    def test_srt_result_selects_only_difference_or_signed_shift(self):
        text = self.sources['ct_vfdsu_srt.v']
        self.assertEqual(assignment(text, 'vfdsu_ex2_expnt_rst'),
                         '(vfdsu_ex2_sqrt)?ex2_sqrt_expnt_result[12:0]:ex2_expnt_result[12:0]')
        self.assertEqual(assignment(text, 'ex2_expnt_result'),
                         'vfdsu_ex2_expnt_add0[12:0]-vfdsu_ex2_expnt_add1[12:0]')
        self.assertEqual(assignment(text, 'ex2_sqrt_expnt_result'),
                         '{ex2_expnt_result[12],ex2_expnt_result[12:1]}')

    def test_driver_extractor_rejects_ambiguous_assignments(self):
        with self.assertRaises(ValueError):
            assignment('assign x[12:0]=a; assign x[12:0]=b;', 'x')
        with self.assertRaises(ValueError):
            assignment('assign y[12:0]=a;', 'x')


if __name__ == '__main__':
    unittest.main()
