import copy
import json
import unittest

import prepare_qbs_payload_zero796 as p


class ZeroPacketTests(unittest.TestCase):
    def test_packet_verification_json_roundtrip(self):
        result = {'writers': [('source', 269)], 'coordinates': [17062, 17063]}
        p.verify_packet(json.loads(json.dumps(result)), result)

    def test_packet_verification_rejects_coordinate_tamper(self):
        result = {'writers': [('source', 269)], 'coordinates': [17062, 17063]}
        packet = json.loads(json.dumps(result))
        packet['coordinates'][0] += 1
        with self.assertRaisesRegex(ValueError, 'full offline recomputation'):
            p.verify_packet(packet, result)

    @classmethod
    def setUpClass(cls):
        cls.ctx = p.context()
        cls.keys, cls.witnesses, cls.counts = p.bank1_domain()
        cls.adapter = (p.ROOT / 'hardware/src/vlsu/qbs/qbs_block_adapter.sv').read_text()
        cls.payload = (p.ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv').read_text()
        cls.compute = (p.ROOT / 'hardware/src/vlsu/qbs/qbs_compute_engine.sv').read_text()

    def partition(self, which, semantic=None, row=None, nodes=None):
        classify = (lambda key, slot, side: side and slot == 0) if which == 'side' else (
            lambda key, slot, side: key[0] == 'activation' and not (side and slot == 0) and key not in self.keys)
        return p.partition(p.SCOPES[1], nodes or self.ctx['nodes'][p.SCOPES[1]],
                           row or self.ctx['union'][p.SCOPES[1]],
                           self.ctx['semantic'] if semantic is None else semantic,
                           classify, 'test-source-sha')

    def test_exact_post_EL_groups_and_disjointness(self):
        mapping, side = self.partition('mapping'), self.partition('side')
        self.assertEqual((mapping['candidate_positions'], side['candidate_positions']), (4112, 3500))
        def coordinates(result):
            return {c for t in result['targets'] for b in t['unowned_bits'] for c in b['raw_zero_coordinates']}
        self.assertFalse(coordinates(mapping) & coordinates(side))
        self.assertEqual(len(coordinates(mapping) | coordinates(side)), 7612)

    def test_full_domain_all_writers_not_fixture_only(self):
        self.assertEqual(self.counts['enumerated'], 2 * 3 * 4 * 1024 * 16)
        self.assertEqual({key[-1] for key in self.keys}, set(range(16)))
        self.assertEqual({key[1] for key in self.keys}, set(range(4)))
        self.assertEqual({w['profile'] for w in self.witnesses.values()}, {'Q8_K', 'Q8_0'})
        self.assertTrue(all(w['layout'] == 'M8' for w in self.witnesses.values()))

    def test_domain_alignment_relaxation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'alignment'):
            p.bank1_domain(step=2)

    def test_ROW_and_M4_cannot_create_bank1_valid_tuple(self):
        for profile in ('Q8_K', 'Q8_0'):
            for layout in ('ROW', 'M4'):
                for context in range(4):
                    for offset in (0, 4, 32, 256, 292, 4092):
                        for writer in range(16):
                            ctx, _, valid = p.route.activation_map(
                                dict(activation_profile=profile, activation_layout=layout), offset + writer, context)
                            self.assertFalse(valid and 4 <= ctx < 8)

    def test_reachable_zero_raw_is_not_a_candidate(self):
        node = next(n for n in self.ctx['nodes'][p.SCOPES[1]] if n['name'] ==
                    'gen_write_merge[1].gen_bank_plane[2].gen_bank_row[0].gen_byte_merge[1].hit')
        key, _, _ = p.congruence.m.identity(node['name'], 0)
        self.assertIn(key, self.keys)
        result = self.partition('mapping', row=dict(width=66340, checksum=p.CHECKSUM, bits='0x0'), nodes=[node])
        records = [t for t in result['targets'] if t['signal'] == node['name']]
        self.assertTrue(records)
        self.assertNotIn(0, [r['bit'] for r in records[0]['source_candidate_bits']])
        self.assertIn(0, records[0]['protected_bit_indices'])

    def test_raw_counterexample_holds_whole_group(self):
        baseline = self.partition('mapping')
        position = baseline['targets'][0]['source_candidate_bits'][0]['raw_zero_coordinates'][0]
        row = dict(self.ctx['union'][p.SCOPES[1]])
        row['bits'] = hex(int(row['bits'], 16) | (1 << (row['width'] - 1 - position)))
        group = p.checked_group('mapping', lambda: self.partition('mapping', row=row), 4112)
        self.assertEqual(group['status'], 'HOLD')
        self.assertEqual(group['targets'], [])
        self.assertEqual(group['candidate_positions'], 0)

    def test_already_EL_owned_raw_counterexample_still_rejected(self):
        result = self.partition('side')
        record = next(b for t in result['targets'] for b in t['both_direction_EL_removed_bits'])
        row = dict(self.ctx['union'][p.SCOPES[1]])
        row['bits'] = hex(int(row['bits'], 16) | (1 << (row['width'] - 1 - record['raw_zero_coordinates'][0])))
        with self.assertRaisesRegex(ValueError, 'counterexample'):
            self.partition('side', row=row)

    def test_compiled_width_drift_holds(self):
        row = dict(self.ctx['union'][p.SCOPES[1]], width=66338)
        self.assertEqual(p.checked_group('side', lambda: self.partition('side', row=row))['status'], 'HOLD')

    def test_compiled_source_line_drift_rejected(self):
        nodes = copy.deepcopy(self.ctx['nodes'][p.SCOPES[1]])
        next(n for n in nodes if n['name'].endswith('.hit'))['line_num'] = '999'
        with self.assertRaisesRegex(ValueError, 'declaration'):
            self.partition('side', nodes=nodes)

    def test_EL_exact_duplicate_is_idempotent(self):
        text = ('CHECKSUM: "1 %s"\nINSTANCE: %s\n'
                'Toggle gen_side_row[0].gen_activation_byte[0].hit [0]\n') % (p.CHECKSUM, p.SCOPES[1])
        self.assertEqual(p.parse_el(text, {}), p.parse_el(text + text, {}))

    def test_EL_both_directions_removed_once(self):
        name = 'test'
        key = (p.SCOPES[1], '1 ' + p.CHECKSUM, name, '', '', (), '0to1')
        semantic = (set(), {key: 4, key[:-1] + ('1to0',): 4})
        self.assertEqual(p.owner_for(p.SCOPES[1], name, 16, semantic), {'0to1': 4, '1to0': 4})

    def test_single_direction_EL_holds_group(self):
        result = self.partition('mapping')
        field = next(t for t in result['targets'] if t['unowned_bits'])
        bit = field['unowned_bits'][0]['bit']
        other, masks = self.ctx['semantic']
        altered = dict(masks)
        altered[(p.SCOPES[1], '1 ' + p.CHECKSUM, field['signal'], '', '', (), '0to1')] = 1 << bit
        self.assertEqual(p.checked_group('mapping', lambda: self.partition('mapping',
                         semantic=(other, altered)))['status'], 'HOLD')

    def test_MDA_EL_not_flattened(self):
        key = (p.SCOPES[1], '1 ' + p.CHECKSUM, 'test', '', '', (0,), '0to1')
        with self.assertRaisesRegex(ValueError, 'MDA'):
            p.owner_for(p.SCOPES[1], 'test', 16, (set(), {key: 1}))

    def test_EL_checksum_conflict_rejected(self):
        key = (p.SCOPES[1], '1 999', 'test', '', '', (), '0to1')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            p.owner_for(p.SCOPES[1], 'test', 16, (set(), {key: 1}))

    def test_EL_range_overflow_rejected(self):
        key = (p.SCOPES[1], '1 ' + p.CHECKSUM, 'test', '', '', (), '0to1')
        with self.assertRaisesRegex(ValueError, 'range'):
            p.owner_for(p.SCOPES[1], 'test', 16, (set(), {key: 1 << 16}))

    def test_whole_scope_ancestor_holds(self):
        # Use the actual dotted ancestor, not a string prefix of bank0/bank1.
        other = {(p.SCOPES[1].rsplit('.', 2)[0], '1', '', 'WHOLE_SCOPE')}
        with self.assertRaisesRegex(ValueError, 'Whole-scope'):
            p.owner_for(p.SCOPES[1], 'test', 16, (other, {}))

    def test_packed_parent_EL_holds(self):
        key = (p.SCOPES[1], '1 ' + p.CHECKSUM, 'parent', '', '', (), '0to1')
        with self.assertRaisesRegex(ValueError, 'parent/child'):
            p.owner_for(p.SCOPES[1], 'parent.hit', 16, (set(), {key: 1}))

    def test_wrong_expected_count_holds_group(self):
        result = p.checked_group('side', lambda: self.partition('side'), 3498)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['targets'], [])

    def test_all_ingress_writers_and_assertion_not_a_writer(self):
        receipt = p.ingress_contract(self.adapter)
        self.assertEqual(len(receipt['activation']), 17)
        self.assertEqual(p.all_writes('assert (a <= 2); assign a = b;', ['a']), [('a', '=', 'b')])

    def test_extra_ingress_writer_rejected(self):
        with self.assertRaisesRegex(ValueError, 'writers'):
            p.ingress_contract(self.adapter + '\nassign activation_ingress_q[0] = forced;\n')

    def test_tuple_reindex_writer_rejected(self):
        bad = self.adapter.replace('activation_ingress_target_q[entry][b] <= activation_input_target[b];',
                                   'activation_ingress_target_q[entry][b] <= activation_input_target[0];')
        self.assertNotEqual(bad, self.adapter)
        with self.assertRaisesRegex(ValueError, 'alternate writer'):
            p.ingress_contract(bad)

    def test_pending_side_capture_mutation_rejected(self):
        bad = self.adapter.replace('activation_pending_q.strb <= activation_remaining[31:16];',
                                   'activation_pending_q.strb <= activation_mask[31:16];')
        self.assertNotEqual(bad, self.adapter)
        with self.assertRaises(ValueError):
            p.side.source_contract(bad, self.payload, self.compute)

    def test_side_not_consumed_mutation_rejected(self):
        bad = self.payload.replace('activation_location[B].plane == 2);',
                                   'activation_location[B].plane == 3);')
        self.assertNotEqual(bad, self.payload)
        with self.assertRaises(ValueError):
            p.side.source_contract(self.adapter, bad, self.compute)

    def test_queue_and_pending_inductions(self):
        self.assertGreater(p.queue_induction()['states'], 1)
        self.assertEqual(p.side.induction_check()['transition_combinations_checked'], 768)

    def test_constant_contract_and_no_fake_coordinates(self):
        p.constant_contract(self.payload, self.compute)
        receipt = p.constant_projection(self.ctx)
        self.assertEqual(receipt['source_proof_status'], 'PASS')
        self.assertEqual(receipt['candidate_positions'], 0)
        self.assertTrue(all(r['raw_coordinates'] is None for r in receipt['source_constants']))
        self.assertTrue(all('HOLD' in r['status'] for r in receipt['source_constants']))
        for r in receipt['source_constants']:
            if r['signal'].startswith(('write_data', 'write_be')):
                self.assertIn(r['signal'].split('[')[2].split(']')[0], ('0', '1'))

    def test_weight_highhalf_nonzero_mutation_rejected(self):
        bad = self.payload.replace("write_data[slot][p][r][255:128] = '0;",
                                   "write_data[slot][p][r][255:128] = '1;")
        self.assertNotEqual(bad, self.payload)
        with self.assertRaises(ValueError):
            p.constant_contract(bad, self.compute)

    def test_NativeView1_mutation_rejected(self):
        bad = self.compute.replace(".NativeView(1'b0)", ".NativeView(1'b1)")
        with self.assertRaisesRegex(ValueError, 'NativeView0'):
            p.constant_contract(self.payload, bad)

    def test_alternate_constant_writer_rejected(self):
        with self.assertRaisesRegex(ValueError, 'writers'):
            p.constant_contract(self.payload + '\nassign write_data[0][0][0] = forced;\n', self.compute)

    def test_new_compiled_constant_requires_successor_binder(self):
        ctx = dict(self.ctx, nodes=dict(self.ctx['nodes']))
        ctx['nodes'][p.SCOPES[0]] = self.ctx['nodes'][p.SCOPES[0]] + [dict(name='write_data[0][0][0]')]
        with self.assertRaisesRegex(ValueError, 'successor'):
            p.constant_projection(ctx)

    def test_allwriters_frozen_source_chain_receipt(self):
        receipt = p.source_receipt(self.ctx)
        self.assertEqual(len(receipt['hit_fanin_all_writers']), 12)
        self.assertEqual(set(receipt['producer_all_writers']),
                         {'qbs_read_engine.sv', 'qbs_engine.sv', 'qbs_activation_context.sv'})
        self.assertFalse(receipt['startup_X_qualified'])

    def test_constant_source_hash_drift_holds(self):
        ctx = dict(self.ctx, book=dict(self.ctx['book']))
        path = str(p.ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv')
        ctx['book'][path] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash'):
            p.constant_projection(ctx)

    def test_cross_group_duplicate_is_atomic_HOLD(self):
        field = dict(scope='scope', unowned_bits=[dict(raw_zero_coordinates=[0, 1])])
        groups = [dict(group='one', status='PREPARED', targets=[field], candidate_positions=2),
                  dict(group='two', status='PREPARED', targets=[field], candidate_positions=2)]
        self.assertEqual(p.deduplicate_groups(groups), {('scope', 0), ('scope', 1)})
        self.assertEqual(groups[1]['status'], 'HOLD')
        self.assertEqual(groups[1]['targets'], [])

    def test_scope_index_preserves_ancestor_and_local_ownership(self):
        local = (p.SCOPES[1], '1 ' + p.CHECKSUM, 'test', '', '', (), '0to1')
        foreign = (p.SCOPES[0], '1 ' + p.CHECKSUM, 'test', '', '', (), '0to1')
        ancestor = (p.SCOPES[1].rsplit('.', 2)[0], '1', '', 'WHOLE_SCOPE')
        other, masks = p.scoped_semantic(p.SCOPES[1], ({ancestor}, {local: 1, foreign: 1}))
        self.assertEqual(other, {ancestor})
        self.assertEqual(masks, {local: 1})

    def test_array_parent_EL_is_not_ignored(self):
        key = (p.SCOPES[1], '1 ' + p.CHECKSUM, 'write_data', '', '', (), '0to1')
        with self.assertRaisesRegex(ValueError, 'parent/child'):
            p.owner_for(p.SCOPES[1], 'write_data[0][0][0]', 256, (set(), {key: 1}))

    def test_weight_read_port_fullwidth_mutation_rejected(self):
        bad = self.payload.replace('localparam int DataWidth = p == 2 ? 256 : 128;',
                                   'localparam int DataWidth = 256;')
        self.assertNotEqual(bad, self.payload)
        with self.assertRaisesRegex(ValueError, 'range contract'):
            p.constant_contract(bad, self.compute)

    def test_upper_byte_loop_mutation_rejected(self):
        bad = self.payload.replace('byte_lane < WordBytes;', 'byte_lane < 32;')
        self.assertNotEqual(bad, self.payload)
        with self.assertRaisesRegex(ValueError, 'range contract'):
            p.constant_contract(bad, self.compute)


if __name__ == '__main__':
    unittest.main()
