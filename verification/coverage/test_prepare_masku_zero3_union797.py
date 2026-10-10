import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_masku_zero3_union797 as m


class UnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = m.q.read_bound(m.native.OUT / 'config.json', m.native.NATIVE_SHA)
        cls.local = (m.native.OUT / 'first.el').read_text()
        cls.base = (m.REPORT796 / 'combined.el').read_text()
        review = m.q.read_bound(m.q.REVIEW, m.q.REVIEW_SHA)
        cls.positions = [p for o in review['objects'] for b in o['bits'] for p in b['serialized_pair']]

    def row(self, bits=0):
        return dict(width=4390, checksum='1400516067', bits=hex(bits))

    def block(self, directives, scope=None, checks='4132557224 1400516067'):
        return 'CHECKSUM: "%s"\nINSTANCE: %s\nANNOTATION: "%s"\n%s\n' % (
            checks, scope or m.q.SCOPE, m.q.ANNOTATION, '\n'.join(directives))

    def test_actual796_retained_native3_precise_union(self):
        combined, delta, info = m.union_gate(self.base, self.local, self.c)
        self.assertTrue(combined.startswith(self.base))
        self.assertEqual(info['added_objects'], list(m.q.NAMES))
        self.assertEqual(info['added_physical_bits'], 768)
        self.assertEqual(info['added_toggle_direction_members'], 1536)
        self.assertEqual(len(m.q.records(delta, self.c)), 3)
        self.assertEqual(m.stable.semantic(combined)[0], m.stable.semantic(self.base)[0])

    def test_physical_dedup_existing_full_vector_retained_not_readded(self):
        name = m.q.NAMES[0]
        inherited = self.block(['Toggle %s "logic %s[255:0]"' % (name, name)])
        combined, delta, info = m.union_gate(inherited, self.local, self.c)
        self.assertEqual(info['already_inherited_objects'], [name])
        self.assertEqual(len(info['added_objects']), 2)
        self.assertEqual(info['added_toggle_direction_members'], 1024)
        self.assertNotIn('Toggle ' + name + ' ', delta)
        self.assertTrue(combined.startswith(inherited))
        all_owned, empty, info = m.union_gate(self.local, self.local, self.c)
        self.assertEqual(all_owned, self.local)
        self.assertEqual(empty, '')
        self.assertEqual(info['added_physical_bits'], 0)

    def test_partial_single_direction_wrong_type_checksum_overlap_hold(self):
        name = m.q.NAMES[0]
        for directives, checks in [(['Toggle 0to1 %s "logic %s[255:0]"' % (name, name)], '4132557224 1400516067'),
                                   (['Toggle %s "logic %s[127:0]"' % (name, name)], '4132557224 1400516067'),
                                   (['Toggle %s "wire %s[255:0]"' % (name, name)], '4132557224 1400516067'),
                                   (['Toggle %s "logic %s[255:0]"' % (name, name)], '1 1400516067')]:
            with self.subTest(directives=directives), self.assertRaises(ValueError):
                m.union_gate(self.block(directives, checks=checks), self.local, self.c)

    def test_whole_scope_ancestor_or_opaque_target_hold(self):
        for base in ['CHECKSUM: "1"\nINSTANCE: ' + m.q.PARENT + '\n',
                     'CHECKSUM: "4132557224 1400516067"\nINSTANCE: ' + m.q.SCOPE + '\n',
                     self.block(['Toggle opaque'])]:
            with self.assertRaises(ValueError): m.union_gate(base, self.local, self.c)

    def test_native_duplicates_metrics_parent_partial_scope_rejected(self):
        line = 'Toggle bit_enable_mask_o "logic bit_enable_mask_o[255:0]"'
        for local in [self.local + line + '\n', self.local.replace(line, ''),
                      self.local.replace('[255:0]', '[254:0]'), self.local.replace('Toggle ', 'Branch '),
                      self.local.replace(m.q.SCOPE, m.q.PARENT), self.local.replace(m.q.ANNOTATION, 'wrong'),
                      self.local + 'INSTANCE: foreign\n']:
            with self.subTest(local=local), self.assertRaises(ValueError):
                m.union_gate(self.base, local, self.c)

    def test_protected_complement_rules_not_modified(self):
        inherited = self.block(['Toggle other_mask "logic other_mask[255:0]"'])
        combined, _, _ = m.union_gate(inherited, self.local, self.c)
        oldother, oldmasks = m.stable.semantic(inherited)
        afterother, aftermasks = m.stable.semantic(combined)
        self.assertEqual(oldother, afterother)
        self.assertTrue(all(aftermasks[k] == v for k, v in oldmasks.items()))
        self.assertTrue(combined.startswith(inherited))

    def test_each_object_each_pair_slot_raw_hit_rejected(self):
        m.zero_row(self.row(), self.positions)
        for p in (2272, 2273, 2783, 3296, 3297, 3807, 3808, 3809, 4319):
            with self.subTest(position=p), self.assertRaises(ValueError):
                m.zero_row(self.row(1 << (4390 - 1 - p)), self.positions)

    def test_raw_shape_checksum_bounds_and_duplicate_positions_rejected(self):
        for mutation in [lambda r: r.update(width=4391), lambda r: r.update(width=True),
                         lambda r: r.update(checksum='1'), lambda r: r.update(bits=hex(1 << 4390))]:
            bad = self.row()
            mutation(bad)
            with self.assertRaises(ValueError): m.zero_row(bad, self.positions)
        for positions in [self.positions[:-1], self.positions[:-1] + [self.positions[0]],
                          self.positions[:-1] + [4390]]:
            with self.assertRaises(ValueError): m.zero_row(self.row(), positions)

    def test_exact797_membership_and_OR_gate_negative(self):
        old = ['design'] + ['test%d' % n for n in range(796)]
        ledger = old + ['suffix797']
        status = dict(coverage_admitted=True, aggregate_passed=797,
                      full_OR_metric_instances=6162, full_OR_Toggle_instances=2989)
        m.population_gate(old, ledger, status, self.row(), self.row(), self.row(), self.positions)
        for changed in [ledger[:-1], ledger[:-1] + [ledger[1]], list(reversed(ledger))]:
            with self.assertRaises(ValueError):
                m.population_gate(old, changed, status, self.row(), self.row(), self.row(), self.positions)
        for key, value in [('coverage_admitted', False), ('aggregate_passed', True),
                           ('aggregate_passed', 796), ('full_OR_Toggle_instances', 2988)]:
            bad = dict(status, **{key: value})
            with self.assertRaises(ValueError):
                m.population_gate(old, ledger, bad, self.row(), self.row(), self.row(), self.positions)
        with self.assertRaises(ValueError):
            m.population_gate(old, ledger, status, self.row(1), self.row(), self.row(), self.positions)

    def test_suffix_or_full797_hit_never_waived(self):
        old = ['design'] + ['test%d' % n for n in range(796)]
        status = dict(coverage_admitted=True, aggregate_passed=797,
                      full_OR_metric_instances=6162, full_OR_Toggle_instances=2989)
        hit = self.row(1 << (4390 - 1 - self.positions[0]))
        for index in range(3):
            rows = [self.row(), self.row(), self.row()]
            rows[index] = hit
            with self.assertRaises(ValueError):
                m.population_gate(old, old + ['suffix'], status, *rows, self.positions)

    def test_prepare_fresh_directory_no_launch_api(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m, 'evidence') as evidence:
            with self.assertRaises(ValueError): m.prepare(Path(td))
            evidence.assert_not_called()
        self.assertFalse(hasattr(m, 'run'))


if __name__ == '__main__': unittest.main()
