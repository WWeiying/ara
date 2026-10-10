import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_gap53_operand_parameters as review


def expression(text='SupportIntExt2', index=1):
    return dict(exprstr=text, index=str(index))


class ParameterNegatives(unittest.TestCase):
    def setUp(self):
        self.parameters = dict.fromkeys(review.SUPPORT, 0)

    def test_only_false_guard_true_demand_is_candidate(self):
        for vector, expected in [('01', 'PARAMETER_FALSE_TRUE_CANDIDATE'),
                                 ('10', 'RETAINED_STIMULUS_REVIEW'),
                                 ('0-', 'RETAINED_STIMULUS_REVIEW')]:
            self.assertEqual(review.decide(vector, [expression()], self.parameters, False)[0], expected)

    def test_index_is_one_based_from_vector_right(self):
        self.assertEqual(len(review.impossible_true('0100', [expression(index=3)], self.parameters)), 1)
        self.assertEqual(review.impossible_true('0100', [expression(index=2)], self.parameters), [])

    def test_enabled_guard_false_arm_is_not_waived(self):
        self.parameters['SupportIntExt2'] = 1
        for vector in ('10', '01', '0-'):
            self.assertEqual(review.decide(vector, [expression()], self.parameters, False)[0],
                             'RETAINED_STIMULUS_REVIEW')

    def test_inactive_false_parent_and_cmd_conversion_not_waived(self):
        exprs = [expression(index=1), expression('cmd.conv', index=2)]
        self.assertEqual(review.decide('010', exprs, self.parameters, False)[0], 'RETAINED_STIMULUS_REVIEW')

    def test_dynamic_or_unknown_expression_is_not_folded(self):
        for text in ('cmd.conv', 'cmd.is_reduct', 'SupportIntExt2 || cmd.valid',
                     'SupportIntExt2 && cmd.valid', 'UnknownParameter',
                     'RVVB(cmd.eew)', '__import__("os")', '1'):
            with self.subTest(text=text):
                self.assertIsNone(review.guard_tree(text))

    def test_half_single_double_is_111000_not_000111(self):
        self.parameters['FPUSupport'] = 56
        for name, expected in [('RVVD', 1), ('RVVF', 1), ('RVVH', 1), ('RVVHA', 0), ('RVVB', 0), ('RVVBA', 0)]:
            self.assertEqual(review.guard_value(review.guard_tree(name + '(FPUSupport)'), self.parameters), expected)
        tree = review.guard_tree('ara_pkg::RVVB(FPUSupport) || ara_pkg::RVVBA(FPUSupport)')
        self.assertEqual(review.guard_value(tree, self.parameters), 0)

    def test_none_and_half_support_guard(self):
        for value, expected in [(0, 0), (56, 1)]:
            self.parameters['FPUSupport'] = value
            self.assertEqual(review.guard_value(review.guard_tree('FPUSupport != FPUSupportNone'), self.parameters), expected)

    def test_guard_tree_normalizes_only_or_grouping(self):
        self.assertEqual(review.guard_tree('(RVVH(FPUSupport) || RVVB(FPUSupport)) || RVVBA(FPUSupport)'),
                         review.guard_tree('RVVH(FPUSupport) || RVVB(FPUSupport) || RVVBA(FPUSupport)'))

    def test_static_impossibility_with_actual_hit_rejects_analysis(self):
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            review.decide('01', [expression()], self.parameters, True)

    def test_reviewed_point_subtracted_even_if_new_rule_matches(self):
        self.assertEqual(review.decide('01', [expression()], self.parameters, False, True)[0], 'ALREADY_REVIEWED')
        with self.assertRaises(ValueError):
            review.decide('10', [expression()], self.parameters, True, True)

    def test_expression_index_bounds(self):
        for index in (0, -1, 3):
            with self.subTest(index=index), self.assertRaises(ValueError):
                review.impossible_true('01', [expression(index=index)], self.parameters)


class MappingNegatives(unittest.TestCase):
    def setUp(self):
        self.definition = ET.fromstring('''<branch_def chksum="77"><wrapper>
          <branch_spec id="4" totalbranches="3"><branch_vector id="7" vector="01"/>
          <branch_vector id="9" vector="10"/><branch_vector id="2" vector="0-"/></branch_spec>
          <branch_spec id="5" totalbranches="2"><branch_vector id="0" vector="01"/>
          <branch_vector id="1" vector="10"/></branch_spec></wrapper></branch_def>''')
        self.raw = dict(width=5, checksum='77', bits='0x15')

    def test_iter_specs_and_reverse_positions_not_vector_ids(self):
        rows = list(review.branch_points(self.definition, self.raw))
        self.assertEqual([(v.get('id'), i, bit) for _, v, i, bit, _, _ in rows],
                         [('7', 2, '1'), ('9', 1, '0'), ('2', 0, '1'), ('0', 4, '1'), ('1', 3, '0')])

    def test_raw_width_checksum_and_overflow_rejected(self):
        for changed in (dict(width=4), dict(checksum='78'), dict(bits='0x20'), dict(bits='-0x1')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                list(review.branch_points(self.definition, dict(self.raw, **changed)))

    def test_missing_raw_checksum_allowed_only_by_bound_definition(self):
        self.assertEqual(len(list(review.branch_points(self.definition, dict(self.raw, checksum=None)))), 5)

    def test_duplicate_vectors_specs_and_bad_encoding_rejected(self):
        for tag, attr, value in [('branch_vector', 'id', '9'), ('branch_vector', 'vector', '0x'),
                                 ('branch_vector', 'vector', '001'), ('branch_spec', 'id', '5'),
                                 ('branch_spec', 'totalbranches', '2')]:
            d = copy.deepcopy(self.definition)
            next(d.iter(tag)).set(attr, value)
            with self.subTest(attr=attr, value=value), self.assertRaises(ValueError):
                list(review.branch_points(d, self.raw))


class SourceAndBindingNegatives(unittest.TestCase):
    def test_nested_type_override_preserves_exact_expression(self):
        text = 'lane #(.NrLanes(NrLanes), .pe_req_t_bits($bits(pe_req_t))) i_lane ('
        entries = review.overrides(text, 'lane')['i_lane']
        self.assertEqual(entries['pe_req_t_bits']['expression'], '$bits(pe_req_t)')
        self.assertEqual(entries['pe_req_t_bits']['source']['text'], '$bits(pe_req_t)')
        with self.assertRaises(ValueError):
            review.overrides(text.replace(', .pe_req', ' .pe_req'), 'lane')

    def test_exact_guard_source_columns_with_nested_calls(self):
        text = '// preface\n  EW8: if (RVVB(FPUSupport) || RVVBA(FPUSupport)) begin\n'
        found = review.if_guard(text, 2)
        self.assertEqual(found['start'], [2, 12])
        self.assertEqual(found['text'], 'RVVB(FPUSupport) || RVVBA(FPUSupport)')
        with self.assertRaises(ValueError):
            review.if_guard('if (A) if (B) x;', 1)

    def test_source_defaults_are_not_zero_assumptions(self):
        text = '\n'.join('parameter logic %s = %s,' % (p, "1'b1" if p == 'SupportNtrVal' else '0') for p in review.PARAMETERS)
        d = review.defaults(text)
        self.assertEqual(review.constant(d['SupportNtrVal']['expression'], {}), 1)
        with self.assertRaises(ValueError):
            review.defaults(text.replace('SupportNtrVal', 'Missing'))

    def test_actual_small_source_parameter_table(self):
        package = review.PACKAGE.read_text()
        env, records = review.package_constants(package)
        env.update(NrLanes=4, VLEN=1024, FPUSupport=56)
        stage = review.overrides(review.STAGE_SOURCE.read_text(), 'operand_queue')
        defaults = review.defaults(review.QUEUE_SOURCE.read_text())
        expected = {'alu_a': (1, 1, 1, 1, 0, 0), 'alu_b': (1, 1, 1, 1, 1, 0),
                    'mfpu_a': (1, 0, 0, 1, 0, 56), 'mfpu_b': (1, 0, 0, 1, 1, 56),
                    'mfpu_c': (1, 0, 0, 1, 1, 56), 'mask_b': (1, 1, 1, 0, 0, 0),
                    'st_mask_a': (0, 0, 0, 0, 0, 0), 'mask_m': (0, 0, 0, 0, 0, 0),
                    'slide_addrgen_a': (0, 0, 0, 0, 0, 0)}
        for queue, values in expected.items():
            params = stage['i_operand_queue_' + queue]
            self.assertEqual(tuple(review.constant(params.get(p, defaults[p])['expression'], env) for p in review.SUPPORT), values)
        with self.assertRaisesRegex(ValueError, 'FP function differs'):
            review.package_constants(package.replace('return e[1];', 'return e[5];'))
        with self.assertRaisesRegex(ValueError, 'FP enum encoding differs'):
            review.package_constants(package.replace("6'b111000", "6'b000111"))

    def test_compiled_signature_mismatch_not_accepted(self):
        params = dict(SupportNtrVal=1, SupportReduct=1, FPUSupport=56)
        d = ET.fromstring('<tgldef name="operand_queue ( parameter SupportNtrVal,SupportReduct=1,FPUSupport=56 ) "/>')
        proof = review.match_signature(params, d)
        self.assertEqual(proof['omitted_values_resolved_from_bound_source'], ['SupportNtrVal'])
        for changed in (dict(FPUSupport=0), dict(SupportReduct=0)):
            with self.assertRaises(ValueError):
                review.match_signature(dict(params, **changed), d)
        d.set('name', 'operand_queue ( parameter SupportNtrVal,SupportReduct,FPUSupport=56 ) ')
        with self.assertRaises(ValueError):
            review.match_signature(params, d)

    def test_unbound_and_changed_file_rejected(self):
        with tempfile.TemporaryDirectory(prefix='gap53-unit-', dir=review.ROOT / 'verification/out') as directory:
            path = Path(directory) / 'source.sv'
            path.write_text('original')
            digest = hashlib.sha256(b'original').hexdigest()
            inputs = review.Inputs()
            with self.assertRaisesRegex(ValueError, 'missing original pin'):
                inputs.bound(path, {})
            inputs.bound(path, {str(path): digest})
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'input hash differs'):
                inputs.bound(path, {str(path): digest})
            with self.assertRaisesRegex(ValueError, 'changed during analysis'):
                inputs.read(path)

    def test_json_string_keys_and_positions_roundtrip(self):
        value = dict(expression=expression(), location=review.span('abc\ndef', 4, 7),
                     coordinate=dict(spec_key='77:4', raw_index=3))
        self.assertEqual(json.loads(json.dumps(value)), value)


if __name__ == '__main__':
    unittest.main()
