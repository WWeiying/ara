import unittest
import xml.etree.ElementTree as ET

import review_fma_arithmetic_scope as review


class ScopeTests(unittest.TestCase):
    def test_numeric_groups(self):
        for name in ('exponent_difference', 'mid_pipe_sum_q', 'operand_a.mantissa', 'norm_shamt', 'product'):
            self.assertIsNotNone(review.group(ET.Element('vectornode', name=name, portnode='0')))

    def test_control_rounding_metadata_preserved(self):
        for name in ('mid_pipe_valid_q', 'inp_pipe_op_q', 'mid_pipe_rnd_mode_q', 'reg_ena',
                     'effective_subtraction', 'round_sticky_bits', 'pre_round_abs', 'rounded_abs',
                     'mid_pipe_sticky_q', 'special_result.sign', 'status_o.NV', 'result_d.mantissa',
                     'out_pipe_result_q[0].mantissa', 'mid_pipe_tag_q[0].operand_a', 'unknown_new_signal'):
            self.assertIsNone(review.group(ET.Element('vectornode', name=name, portnode='0')))

    def test_port_never_selected_even_if_numeric_name(self):
        self.assertIsNone(review.group(ET.Element('vectornode', name='product', portnode='3')))

    def test_array_bounds_scalar_and_vector(self):
        node = ET.Element('arrays', name='mid_pipe_sum_q', packedrange='0 2 75 0 ', unpackedrange='')
        self.assertEqual(review.width(node), 228)
        self.assertEqual(review.native_name(node), 'mid_pipe_sum_q[0:2][75:0]')
        self.assertEqual(review.width(ET.Element('node', name='final_sign')), 1)
        self.assertEqual(review.width(ET.Element('vectornode', name='product', left='47', right='0')), 48)

    def test_bad_array_shape_rejected(self):
        with self.assertRaises(Exception):
            review.dimensions(ET.Element('arrays', packedrange='0 2 75'))


if __name__ == '__main__':
    unittest.main()
