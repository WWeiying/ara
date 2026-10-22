import copy
import unittest
from lzc_selector_candidates import structural_decision, selector_expression
from lzc_padding_proof import SOURCE_SHA256


def point(level=2, index=3):
    expr = selector_expression(level, index)
    return dict(line='95', vector='1', spec=dict(generate_info=f'level={level},l={index}'),
                metric_checksum='3513283519', source_sha256=SOURCE_SHA256,
                attributes=dict(optype='16', exprstr=expr, width='1'), expression=expr,
                truth_table=dict(ncols='1', nrows='2', vecs='01'))


class SelectorTests(unittest.TestCase):
    def test_padding_candidate(self):
        self.assertEqual(structural_decision(point()), 'STRUCTURAL_CANDIDATE_NATIVE_REQUIRED')

    def test_real_left_retained(self):
        self.assertEqual(structural_decision(point(1, 0)), 'RETAIN_REACHABLE')

    def test_false_row_retained(self):
        p = point(); p['vector'] = '0'
        self.assertEqual(structural_decision(p), 'RETAIN')

    def test_ternary_not_auto_qualified(self):
        p = point(); p['attributes']['optype'] = '23'
        self.assertEqual(structural_decision(p), 'HOLD_TERNARY_NATIVE_SEMANTICS')

    def test_wrong_source_rejected(self):
        p = point(); p['source_sha256'] = 'bad'
        with self.assertRaises(ValueError): structural_decision(p)

    def test_wrong_expression_rejected(self):
        p = point(); p['expression'] = '1'
        with self.assertRaises(ValueError): structural_decision(p)

    def test_wrong_truth_table_rejected(self):
        p = point(); p['truth_table']['vecs'] = '10'
        with self.assertRaises(ValueError): structural_decision(p)

    def test_invalid_node_rejected(self):
        with self.assertRaises(ValueError): structural_decision(point(8, 9))


if __name__ == '__main__':
    unittest.main()
