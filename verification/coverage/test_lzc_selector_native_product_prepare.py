"""Offline boundary tests, no simulator or DVE invocation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import lzc_selector_native_product_prepare as product


class ProductPrepareTests(unittest.TestCase):
    def setUp(self):
        branch = json.loads((product.OUT / 'lzc-selector-branch-candidates-705-20261006-01.json').read_text())['rows'][0]
        conds = json.loads((product.OUT / 'lzc-selector-condition-candidates-705-20261006-01.json').read_text())['rows']
        point = next(r['point'] for r in conds if r['decision'] == 'HOLD_TERNARY_NATIVE_SEMANTICS'
                     and r['point']['scope'] == branch['scope']
                     and r['point']['spec']['generate_info'] == branch['point']['attributes']['generate_info'])
        self.branch = product.candidate_record(branch['scope'], 'branch', branch['point'],
                                              branch['parameters'], '3250293308', branch['metric_checksum'])
        self.cond = product.candidate_record(branch['scope'], 'cond', point,
                                            branch['parameters'], '3250293308', point['metric_checksum'])

    def condition_el(self, candidate=None, identity='901', vector_id='907', vector='1'):
        c = candidate or self.cond
        return (f'CHECKSUM: "{c["module_checksum"]} {c["metric_checksum"]}"\n'
                f'INSTANCE: {c["scope"]}\n'
                f'Condition {identity} "{c["point_checksum"]}" "{c["expression"]} 1 -1" '
                f'({vector_id} "{vector}")\n')

    def branch_el(self, candidate=None, arm='0', signature_value='1'):
        c = candidate or self.branch
        return (f'CHECKSUM: "{c["module_checksum"]} {c["metric_checksum"]}"\n'
                f'INSTANCE: {c["scope"]}\n'
                f'Branch 901 "{c["point_checksum"]}" "{c["expression"]}" '
                f'({arm}) "{c["expression"]} {signature_value}"\n')

    def test_native_ids_are_unset_and_learned_not_transferred(self):
        for c in (self.branch, self.cond):
            self.assertIsNone(c['native_id'])
            self.assertIsNone(c['native_vector_id'])
            self.assertFalse(c['native_qualified'])
        record = product.validate_condition_singleton(self.condition_el(), self.cond)
        self.assertEqual((record['native_id'], record['vector_id']), ('901', '907'))
        self.assertEqual(product.validate_branch_singleton(self.branch_el(), self.branch)['native_id'], '901')

    def test_foreign_parent_root_or_checksum_rejected(self):
        for field, value in (('scope', self.cond['scope'].rsplit('.', 1)[0]),
                             ('scope', 'lzc_selector_native_w10_s0_p0.dut'),
                             ('module_checksum', '438741478'), ('metric_checksum', '0'),
                             ('point_checksum', '0'), ('expression', '(fake_selector == 1)')):
            changed = dict(self.cond, **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                product.validate_condition_singleton(self.condition_el(changed), self.cond)

    def test_false_condition_or_false_branch_never_capture(self):
        with self.assertRaises(ValueError):
            product.validate_condition_singleton(self.condition_el(vector='0'), self.cond)
        for arm, signature in (('1', '0'), ('0', '0'), ('1', '1')):
            with self.subTest(arm=arm, signature=signature), self.assertRaises(ValueError):
                product.validate_branch_singleton(self.branch_el(arm=arm, signature_value=signature), self.branch)

    def test_op16_stays_hold(self):
        point = copy.deepcopy(self.cond['xml_provenance'])
        point['attributes']['optype'] = '16'
        with self.assertRaises(ValueError):
            product.eligible(point, 10, 'cond')

    def test_reachable_or_wrong_shape_rejected(self):
        for field in ('coordinates', 'expression', 'truth_table', 'vector'):
            point = copy.deepcopy(self.cond['xml_provenance'])
            if field == 'coordinates':
                point['spec']['generate_info'] = 'level=0,l=0'
                point['expression'] = product.ternary_expression(0, 0)
                point['attributes']['exprstr'] = point['expression']
            elif field == 'truth_table':
                point[field]['vecs'] = '10'
            else:
                point[field] = '0'
            with self.subTest(field=field), self.assertRaises(ValueError):
                product.eligible(point, 10, 'cond')

    def test_collateral_or_whole_instance_rejected(self):
        for text in (self.condition_el() + self.condition_el(identity='902'),
                     self.condition_el().split('Condition')[0]):
            with self.assertRaises(ValueError):
                product.validate_condition_singleton(text, self.cond)
        for text in (self.branch_el() + self.branch_el(), self.branch_el().split('Branch')[0]):
            with self.assertRaises(ValueError):
                product.validate_branch_singleton(text, self.branch)

    def test_exact_child_and_parameters_required(self):
        for scope, params in ((self.branch['scope'].rsplit('.', 1)[0], self.branch['parameters']),
                              (self.branch['scope'], dict(self.branch['parameters'], MODE=0))):
            with self.assertRaises(ValueError):
                product.candidate_record(scope, 'branch', self.branch['xml_provenance'], params, '1', '2')

    def test_invalid_output_rejected_before_work(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            product.prepare(Path(directory) / 'not_in_workspace')


if __name__ == '__main__':
    unittest.main()
