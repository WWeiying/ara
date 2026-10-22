"""Offline capture-contract tests. EL strings here are fixtures, never evidence."""
import copy
import json
import unittest

import lzc_selector_native_product_capture_prepare as capture


class CapturePrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        static = json.loads((capture.product.OUT / 'lzc_selector_native_product_prepare-707-20261006-01/product-plan.json').read_bytes())
        inventory = json.loads((capture.product.OUT / 'lzc_selector_native_product_discovery-707-20261006-03/native-inventory-parent-verified.json').read_bytes())
        cls.rows = capture.protection_rows(inventory)
        cls.branch = next(r for r in static['targets'] if r['metric'] == 'branch')
        cls.cond = next(r for r in static['targets'] if r['metric'] == 'cond')

    def condition_el(self, c=None, vector='1', identity='901', vector_id='907'):
        c = c or self.cond
        return (f'CHECKSUM: "{c["module_checksum"]} {c["metric_checksum"]}"\n'
                f'INSTANCE: {c["scope"]}\n'
                f'Condition {identity} "{c["point_checksum"]}" "{c["expression"]} 1 -1" '
                f'({vector_id} "{vector}")\n').encode('ascii')

    def observations(self, identity='11'):
        c = self.branch
        return [dict(scope=c['scope'], expression=c['expression'], module_checksum=c['module_checksum'],
                     expression_source='native_parent_text', raw_parent_text=c['expression'],
                     parent_path='Item' + identity, native_id=identity, arms=['0', '1'])]

    def branch_el(self, identity='11', arm='0', value='1'):
        c = self.branch
        return (f'CHECKSUM: "{c["module_checksum"]} {c["metric_checksum"]}"\n'
                f'INSTANCE: {c["scope"]}\n'
                f'Branch {identity} "{c["point_checksum"]}" "{c["expression"]}" '
                f'({arm}) "{c["expression"]} {value}"\n').encode('ascii')

    def test_complete_global_protection_rows(self):
        self.assertEqual(len(self.rows), 4200)
        self.assertEqual(sum(r['metric'] == 'branch' for r in self.rows), 1200)
        self.assertEqual(sum(r['metric'] == 'cond' for r in self.rows), 3000)

    def test_condition_signature_learns_both_numeric_ids(self):
        raw = self.condition_el()
        bound = capture.bind_signature(raw, raw, self.cond, self.rows)
        self.assertEqual(bound['native_record']['native_id'], '901')
        self.assertEqual(bound['native_record']['vector_id'], '907')
        self.assertFalse(bound['qualification_complete'])
        self.assertFalse(bound['application_approval'])

    def test_false_or_wrong_exact_condition_signature_rejected(self):
        with self.assertRaises(ValueError):
            raw = self.condition_el(vector='0')
            capture.bind_signature(raw, raw, self.cond, self.rows)
        for field, value in (('scope', self.cond['scope'].rsplit('.', 1)[0]),
                             ('module_checksum', '438741478'), ('point_checksum', '0'),
                             ('metric_checksum', '0'), ('expression', '(other_selector == 1)')):
            raw = self.condition_el(dict(self.cond, **{field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                capture.bind_signature(raw, raw, self.cond, self.rows)

    def test_byte_roundtrip_must_match(self):
        raw = self.condition_el()
        with self.assertRaises(ValueError):
            capture.bind_signature(raw, raw + b'\n', self.cond, self.rows)

    def test_condition_collateral_entry_rejected(self):
        raw = self.condition_el() + self.condition_el(identity='902')
        with self.assertRaises(ValueError):
            capture.bind_signature(raw, raw, self.cond, self.rows)

    def test_branch_cannot_fall_back_to_xml_id_without_expression_preflight(self):
        raw = self.branch_el(identity=self.branch['xml_provenance']['native_id'])
        with self.assertRaises(ValueError):
            capture.bind_signature(raw, raw, self.branch, self.rows)

    def test_branch_id_comes_from_exact_independent_native_parent(self):
        raw = self.branch_el()
        bound = capture.bind_signature(raw, raw, self.branch, self.rows, self.observations())
        self.assertEqual(bound['native_record']['native_id'], '11')
        self.assertNotEqual(bound['native_record']['native_id'], self.branch['xml_provenance']['native_id'])

    def test_branch_ambiguous_foreign_or_unobserved_preflight_rejected(self):
        fixtures = [self.observations() * 2, self.observations('999'), []]
        for field, value in (('raw_parent_text', 'prefix ' + self.branch['expression']),
                             ('expression_source', 'xml'), ('module_checksum', '438741478'),
                             ('arms', ['0']), ('parent_path', 'Item6')):
            changed = self.observations()
            changed[0][field] = value
            fixtures.append(changed)
        for observations in fixtures:
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                capture.resolve_branch(self.branch, observations, self.rows)

    def test_branch_false_or_unresolved_saved_id_rejected(self):
        for identity, arm, value in (('11', '1', '0'), ('11', '0', '0'), ('6', '0', '1')):
            raw = self.branch_el(identity, arm, value)
            with self.subTest(identity=identity, arm=arm, value=value), self.assertRaises(ValueError):
                capture.bind_signature(raw, raw, self.branch, self.rows, self.observations())

    def test_collateral_global_native_state_rejected(self):
        position = capture.condition_position(self.cond, self.rows)
        actual = [dict(position=str(i), scope=r['scope'], metric=r['metric'],
                       native_id=r['native_id'] or '', expression=r['expression'] or '',
                       vector=r['vector'], excluded=str(int(i == position))) for i, r in enumerate(self.rows)]
        capture.verify_states(actual, self.rows, position)
        for mutation in ('extra', 'missing', 'false_excluded', 'wrong_identity'):
            changed = copy.deepcopy(actual)
            if mutation == 'extra':
                changed.append(changed[0])
            elif mutation == 'missing':
                changed.pop()
            elif mutation == 'false_excluded':
                changed[0]['excluded'] = '1'
            else:
                changed[position]['expression'] = 'wrong'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                capture.verify_states(changed, self.rows, position)

    def test_op16_cannot_enter_signature_capture(self):
        c = copy.deepcopy(self.cond)
        c['xml_provenance']['attributes']['optype'] = '16'
        raw = self.condition_el()
        with self.assertRaises(ValueError):
            capture.bind_signature(raw, raw, c, self.rows)


if __name__ == '__main__':
    unittest.main()
