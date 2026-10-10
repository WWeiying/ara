import copy
import json
import unittest
import admit_fpu_matrix_after747 as a


class ExactPrefix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((a.BASE / 'combined-bits.json').read_bytes())
        cls.single = json.loads((a.q.OUT / 'sew16_RF/single-bits.json').read_bytes())

    def test_actual_747_prefix_preserves_aux(self):
        result = a.append(self.before, [self.single])
        self.assertEqual(result['tests'][:747], self.before['tests'])
        self.assertEqual(result['tests'][-1], self.single['tests'][0])
        self.assertEqual(len(result['tests']), 748)

    def test_746_not_authoritative(self):
        bad = copy.deepcopy(self.before); bad['tests'].pop()
        with self.assertRaisesRegex(ValueError, '747'):
            a.append(bad, [self.single])

    def test_duplicate_and_existing_aux_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            a.append(self.before, [self.single, self.single])
        single = copy.deepcopy(self.single); single['tests'] = [self.before['tests'][-1]]
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            a.append(self.before, [single])

    def test_foreign_design_and_missing_scope(self):
        single = copy.deepcopy(self.single); single['design'] = {}
        with self.assertRaisesRegex(ValueError, 'universe'):
            a.append(self.before, [single])
        single = copy.deepcopy(self.single); single['metrics']['fsm'].pop(next(iter(single['metrics']['fsm'])))
        with self.assertRaisesRegex(ValueError, 'universe'):
            a.append(self.before, [single])

    def test_full6162_or_and_identity_drift(self):
        result = a.append(self.before, [self.single]); count = 0
        for metric, rows in self.before['metrics'].items():
            for scope, old in rows.items():
                self.assertEqual(int(result['metrics'][metric][scope]['bits'], 16),
                    int(old['bits'], 16) | int(self.single['metrics'][metric][scope]['bits'], 16)); count += 1
        self.assertEqual(count, 6162)
        single = copy.deepcopy(self.single); single['metrics']['fsm'][next(iter(single['metrics']['fsm']))]['width'] += 1
        with self.assertRaises(ValueError):
            a.append(self.before, [single])


if __name__ == '__main__':
    unittest.main()
