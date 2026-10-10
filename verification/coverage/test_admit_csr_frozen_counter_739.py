import copy
import unittest
from unittest.mock import patch

import admit_csr_frozen_counter_739 as a


def samples():
    scope = a.q.runner.oracle.inventory.SCOPE
    # Full universe with small inert rows and the exact three CSR metric shapes.
    metrics = dict(line={scope: dict(width=974, checksum='2614139268', bits='0x0')},
                   cond={scope: dict(width=571, checksum='2216075028', bits='0x0')},
                   branch={scope: dict(width=626, checksum='3035350189', bits='0x0')}, fsm={})
    for i in range(6159):
        metrics['line'][scope + '.test' + str(i)] = dict(width=1, checksum='1', bits='0x0')
    before = dict(design={'synthetic': 'fixed'}, tests=['old' + str(i) for i in range(738)],
                  input_hashes={str(a.life.OUT / 'synthetic-old-metric'): '0' * 64}, metrics=metrics)
    single = copy.deepcopy(before)
    single['tests'] = [str(a.q.RUN / 'code.vdb')]
    single['input_hashes'] = {str(a.life.OUT / 'synthetic-new-metric'): '1' * 64}
    for m, ids in (('line', (275, 578, 585, 589)), ('cond', (90, 92)), ('branch', (202,))):
        row = single['metrics'][m][scope]
        row['bits'] = hex(sum(1 << (row['width'] - 1 - raw) for raw in ids))
    pre = a.life.read_bound(a.q.runner.PRE / 'target-before.json',
        a.life.read_bound(a.q.runner.PRE / 'preflight-manifest.json', a.q.runner.PRE_SEAL)['output_pins']
        [str(a.q.runner.PRE / 'target-before.json')])
    return before, single, pre['targets']


class AdmissionTests(unittest.TestCase):
    def test_actual_qualification_gate(self):
        a.qualification_gate(a.life.read_bound(a.QUAL, a.QUAL_SEAL))

    def test_missing_scalar_evidence(self):
        proof = a.life.read_bound(a.QUAL, a.QUAL_SEAL)
        proof['full_scalar_differential_qualified'] = False
        with self.assertRaises(ValueError):
            a.qualification_gate(proof)

    def test_bool_int_scope_rejected(self):
        proof = a.life.read_bound(a.QUAL, a.QUAL_SEAL)
        proof['coverage_admitted'] = 0
        with self.assertRaises(ValueError):
            a.qualification_gate(proof)

    def test_missing_output_pin(self):
        proof = a.life.read_bound(a.QUAL, a.QUAL_SEAL)
        proof['output_pins'].pop(str(a.QUAL.parent / 'architecture-audit.json'))
        with self.assertRaises(ValueError):
            a.qualification_gate(proof)

    def test_exact_prefix_full_or(self):
        before, single, _ = samples()
        combined, delta = a.union(before, single)
        self.assertEqual(combined['tests'], before['tests'] + single['tests'])
        self.assertEqual(sum(len(rows) for rows in combined['metrics'].values()), 6162)
        self.assertEqual(sum(delta['metrics'].values()), 7)

    def reject_union(self, change):
        before, single, _ = samples()
        change(before, single)
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_zero_gain_rejected(self):
        self.reject_union(lambda old, single: single.__setitem__('metrics', copy.deepcopy(old['metrics'])))

    def test_duplicate_member(self):
        self.reject_union(lambda old, single: old['tests'].__setitem__(0, single['tests'][0]))

    def test_wrong_population(self):
        self.reject_union(lambda old, single: old['tests'].pop())

    def test_missing_instance(self):
        self.reject_union(lambda old, single: single['metrics']['line'].popitem())

    def test_checksum_drift(self):
        self.reject_union(lambda old, single: next(iter(single['metrics']['line'].values()))
                          .__setitem__('checksum', 'changed'))

    def test_width_drift(self):
        self.reject_union(lambda old, single: next(iter(single['metrics']['line'].values()))
                          .__setitem__('width', 975))

    def test_new_design_rejected(self):
        self.reject_union(lambda old, single: single.__setitem__('design', {'new': 'image'}))

    def test_conflicting_pin(self):
        def mutate(old, single):
            old['input_hashes'][str(a.life.OUT / 'synthetic-alias')] = '0' * 64
            single['input_hashes'][str(a.life.OUT / 'synthetic-alias')] = '1' * 64
        self.reject_union(mutate)

    def test_all_seven_targets(self):
        before, single, targets = samples()
        self.assertTrue(all(h['single_hit'] and not h['before_hit'] for h in a.target_hits(before, single, targets)))

    def test_missing_primary_hit(self):
        before, single, targets = samples()
        single['metrics']['cond'][targets[0]['scope']]['bits'] = '0x0'
        with self.assertRaises(ValueError):
            a.target_hits(before, single, targets)

    def test_wrong_scope(self):
        before, single, targets = samples()
        targets[0]['scope'] += '.injected'
        with self.assertRaises(ValueError):
            a.target_hits(before, single, targets)

    def test_admission_authorization_required(self):
        with patch.object(a, 'evaluate', side_effect=AssertionError('Must not evaluate or write')):
            with self.assertRaises(ValueError):
                a.main(['admit', '--output', str(a.life.OUT / 'not-admitted'), '--prepared-seal', '0' * 64])


if __name__ == '__main__':
    unittest.main()
