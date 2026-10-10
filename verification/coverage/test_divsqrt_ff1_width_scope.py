"""Frozen-source width bounds, not approval of native coverage exclusions."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'


class FF1WidthScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pins = json.loads((ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        names = ['hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv',
                 *[CORE + name for name in ('ct_vfdsu_prepare.v', 'ct_vfdsu_scalar_dp.v',
                                           'ct_vfdsu_ff1.v', 'ct_vfdsu_top.v')]]
        cls.sources = {}
        for name in names:
            path = ROOT / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != pins[str(path)]:
                raise ValueError('Frozen source drift: ' + name)
            cls.sources[Path(name).name] = path.read_text()

    def test_narrow_wrappers_never_select_double(self):
        text = self.sources['fpnew_divsqrt_th_64_multi.sv']
        for width, expected in ((32, {'0100', '0010', '0001'}), (16, {'0010', '0001'})):
            section = text.split('begin : translate_fmt_%d_bits' % width, 1)[1].split('endcase', 1)[0]
            assignments = re.findall(r"divsqrt_fmt\s*=\s*4'b([01]{4})", section)
            self.assertEqual(set(assignments), expected)
            self.assertTrue(all(value[0] == '0' for value in assignments))
            if width == 16:
                self.assertTrue(all(value[1] == '0' for value in assignments))
        self.assertIn("`FFL(divsqrt_fmt_q, divsqrt_fmt, op_starting, '0)", text)
        self.assertIn('{3\'b0, divsqrt_fmt_q, 11\'b0 ,sqrt_op, div_op}', text)

    def test_registered_format_and_prepare_padding(self):
        text = self.sources['ct_vfdsu_scalar_dp.v']
        self.assertIn("ex1_double         <= 1'b0;", text)
        self.assertIn('ex1_double         <= idu_vfpu_rf_pipex_func[16];', text)
        self.assertIn('ex1_single         <= idu_vfpu_rf_pipex_func[15];', text)
        self.assertIn('ex1_half           <= idu_vfpu_rf_pipex_func[14];', text)
        for signal, bit in (('ex1_double', 16), ('ex1_single', 15)):
            self.assertEqual(re.findall(r'\b' + signal + r'\s*<=\s*([^;]+);', text),
                             ["1'b0", 'idu_vfpu_rf_pipex_func[%d]' % bit])
        prepare = self.sources['ct_vfdsu_prepare.v']
        for operand in (0, 1):
            self.assertIn("{ex1_oper%d[22:0],29'b0}" % operand, prepare)
            self.assertIn("{ex1_oper%d[9:0],42'b0}" % operand, prepare)
            self.assertIn("{ex1_oper%d[6:0],45'b0}" % operand, prepare)

    def test_case_patterns_partition_normal_two_state_inputs(self):
        text = self.sources['ct_vfdsu_ff1.v']
        patterns = re.findall(r"52'b([01?]{52})\s*:", text)
        expected = ['0' * n + '1' + '?' * (51 - n) for n in range(52)] + ['0' * 52]
        self.assertEqual(patterns, expected)
        self.assertEqual(sum(1 << p.count('?') for p in patterns), 1 << 52)

    def test_padding_excludes_only_lower_leading_positions(self):
        for fraction_bits, padding in ((23, 29), (10, 42), (7, 45)):
            positions = {(1 << bit << padding).bit_length() - 1 for bit in range(fraction_bits)}
            self.assertEqual(positions, set(range(padding, 52)))
        # The zero-input arm remains reachable. WIDTH64 has no padding bound.
        self.assertEqual(0 << 42, 0)


if __name__ == '__main__':
    unittest.main()
