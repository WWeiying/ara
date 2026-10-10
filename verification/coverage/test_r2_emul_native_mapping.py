import copy
import json
import unittest

import r2_emul_native_mapping as mapping


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.targets = json.loads((mapping.PREFLIGHT / 'target-reconciliation721.json').read_text())
        self.metrics = json.loads((mapping.BASE / 'combined-bits.json').read_text())['metrics']
        self.mapped = {m: {t['point']['raw_index']: copy.deepcopy(t['point'])
                           for t in self.targets if t['metric'] == m} for m in ('line', 'branch')}

    def test_legal_bound_not_vill_hit(self):
        rows = mapping.legal_proof()
        self.assertEqual(len(rows), 88)
        self.assertFalse(any(r['sew'] == 64 and r['lmul'] == '1/8' for r in rows))
        self.assertEqual(min(mapping.Fraction(r['emul']) for r in rows), mapping.Fraction(1, 8))

    def test_exact_roles_no_native_promotion(self):
        result = mapping.bind_targets(self.targets, self.mapped, self.metrics)
        self.assertEqual(sum(t['role'] == 'LOWER_HOLD' for t in result), 4)
        self.assertEqual(sum(t['role'] == 'UPPER_PROTECTED' for t in result), 2)
        self.assertTrue(all(not t['actual_native_identity_qualified'] for t in result))

    def test_reject_expression_vector_and_scope_drift(self):
        for field in ('expression', 'vector'):
            changed = copy.deepcopy(self.mapped)
            changed['branch'][360][field] += 'DRIFT'
            with self.assertRaisesRegex(ValueError, 'signature drift'):
                mapping.bind_targets(self.targets, changed, self.metrics)
        changed = copy.deepcopy(self.targets)
        changed[0]['scope'] += '.wrong_child'
        with self.assertRaisesRegex(ValueError, 'scope drift'):
            mapping.bind_targets(changed, self.mapped, self.metrics)

    def test_reject_hit_checksum_missing_or_promoted_hold(self):
        changed = copy.deepcopy(self.metrics)
        row = changed['line'][mapping.SCOPE]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (row['width'] - 1 - 1228)))[2:]
        with self.assertRaisesRegex(ValueError, 'target hit'):
            mapping.bind_targets(self.targets, self.mapped, changed)
        changed = copy.deepcopy(self.metrics)
        changed['line'][mapping.SCOPE]['checksum'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'metric drift'):
            mapping.bind_targets(self.targets, self.mapped, changed)
        with self.assertRaisesRegex(ValueError, 'exact six'):
            mapping.bind_targets(self.targets[:-1], self.mapped, self.metrics)
        changed = copy.deepcopy(self.targets)
        changed[0]['scope_status'] = 'APPROVED'
        with self.assertRaisesRegex(ValueError, 'classification drift'):
            mapping.bind_targets(changed, self.mapped, self.metrics)


if __name__ == '__main__':
    unittest.main()
