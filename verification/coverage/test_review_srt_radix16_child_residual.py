"""Actual source/shape/dedup review and serialization negative regressions."""
import copy
import json
import unittest

import review_srt_radix16_child_residual as s

REPORT = s.OUT / 'srt-radix16-child-residual-source-review762-agent-20261007-01.json'


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(REPORT.read_bytes())

    def test_actual_pins(self):
        for path, sha in self.r['pins'].items():
            with self.subTest(path=path):
                self.assertEqual(s.digest(path), sha)

    def test_exact_no_duplicate_successor(self):
        r = self.r
        self.assertEqual(r['exact_successor_targets'], [])
        self.assertEqual(r['estimated_new_missing_directions'], 0)
        self.assertFalse(r['native_preparation_justified'])
        scopes = [x for c in r['existing_native_captures'] for x in c['scopes']]
        self.assertEqual(len(set(scopes)), 16)
        self.assertTrue(all(x.endswith('.x_ct_vfdsu_srt_radix16_with_sqrt') for x in scopes))
        self.assertEqual(len(r['held_scalar_instances']), 1)
        self.assertNotIn(r['held_scalar_instances'][0], scopes)

    def test_exact_full_scope_complement(self):
        r = self.r
        arithmetic = r['arithmetic_fields']
        protected = r['protected_local_shape']
        self.assertEqual(len(arithmetic), 158)
        self.assertEqual(len(protected), 52)
        names = {s.native_name(n) for n in arithmetic + protected}
        self.assertEqual(len(names), 210)
        scopes = r['successor_protection_complement']['local_scope_fields']
        self.assertEqual(len(scopes), 17)
        for scope in scopes:
            self.assertEqual(set(scope['names']), names)
        self.assertTrue(r['protected_descendant_instances'])
        self.assertFalse(r['RTL_modified'])
        self.assertFalse(r['native_qualification_started'])

    def test_ports_boundaries_modes_retained(self):
        p = {n['name']: n for n in self.r['protected_local_shape']}
        for name in ('cpurst_b', 'srt_sel_div', 'srt_sel_sqrt', 'bound_sel',
                     'bound_cmp_sign', 'part_rem', 'qt_rt_const_shift_std',
                     'qt_rt_const_shift_std_next', 'srt_remainder', 'total_qt_rt',
                     'initial_divisor_in', 'srt_div_clk_en'):
            self.assertIn(name, p)
        self.assertTrue(all('digit_bound_%d' % n in p for n in range(1, 10)))
        self.assertTrue(all(n['portnode'] == '0' for n in self.r['arithmetic_fields']))

    def test_actual762_direction_accounting(self):
        r = self.r
        self.assertEqual(r['suffix_native_files_verified'], 21)
        self.assertEqual(len(r['latest_raw_scope_records']), 17)
        count = 0
        for record in r['latest_raw_scope_records']:
            self.assertEqual(record['raw_width'], 20656)
            total = 0
            for n in record['fields']:
                actual = s.direction_missing(int(record['raw_bits'], 16), 20656, n)
                self.assertEqual(actual, n['missing_directions'])
                self.assertEqual(actual['pair_slot0'] + actual['pair_slot1'], actual['total'])
                total += actual['total']
            self.assertEqual(total, record['missing_directions'])
            self.assertEqual(total, record['already_qualified_arithmetic_missing'] + record['retained_missing'])
            count += total
        self.assertEqual(count, r['all_local_raw_missing_directions'])

    def test_source_evidence_not_name_only(self):
        r = self.r
        self.assertTrue(r['frozen_source']['upstream_bytes_equal'])
        self.assertEqual(r['compiled_module']['chksum'], '406590228')
        self.assertEqual(r['toggle_definition']['chksum'], '3969040510')
        self.assertEqual([x['kind'] for x in r['evidence']],
                         ['FP32_DIV', 'FP32_SQRT', 'FP64_DIV', 'FP64_SQRT'])
        for e in r['evidence']:
            self.assertEqual(e['exact_arithmetic_requests'], 30)
            self.assertEqual(e['exact_arithmetic_bytes'], 3840)
            self.assertEqual(e['unobservable_zero_byte_arithmetic_requests'], 15)

    def test_partition_rejects_scalar_port_partial_unknown_duplicate(self):
        nodes = self.r['arithmetic_fields'] + self.r['protected_local_shape']
        names = {x['name'] for x in self.r['arithmetic_fields']}
        for new_name in ('cpurst_b', 'srt_remainder', 'digit_bound_1', 'srt_divisor[3:0]', 'unknown'):
            with self.subTest(name=new_name), self.assertRaises(ValueError):
                s.partition(nodes, names | {new_name})
        with self.assertRaises(ValueError):
            s.partition(nodes + [copy.deepcopy(nodes[0])], names)

    def test_pair_offset_and_both_directions(self):
        node = dict(raw_offset=2, width=3)
        self.assertEqual(s.direction_missing(0, 10, node)['total'], 6)
        self.assertEqual(s.direction_missing(0b1111111111, 10, node)['total'], 0)
        mask = 0b101010 << 2
        self.assertEqual(s.direction_missing(mask, 10, node),
                         dict(pair_slot0=0, pair_slot1=3, total=3))


if __name__ == '__main__':
    unittest.main()
