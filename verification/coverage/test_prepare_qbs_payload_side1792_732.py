"""Exact1792 negative gates and exhaustive bit induction; no DVE fixtures invented."""
import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_qbs_payload_side1792_732 as p


class ProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(p.PARENT.read_bytes())
        cls.old = json.loads((p.OLD/'combined-bits.json').read_bytes())
        cls.new = json.loads((p.BASE/'combined-bits.json').read_bytes())
        cls.manifest = json.loads((p.BASE/'admission-manifest.json').read_bytes())
        cls.state = json.loads((p.BASE/'status.json').read_bytes())
        cls.candidates, cls.guards, cls.scopes = p.inventory(p.compiled.Design(p.DESIGN), cls.old, cls.new, cls.original)
        cls.groups = p.groups(cls.candidates, cls.guards)
        cls.texts = {k: (p.ROOT/name).read_text() for k,name in dict(
            adapter='hardware/src/vlsu/qbs/qbs_block_adapter.sv',
            payload='hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
            engine='hardware/src/vlsu/qbs/qbs_compute_engine.sv').items()}

    def test_parent_artifact_seal(self):
        self.assertEqual(p.digest(p.PARENT), p.PARENT_SHA)

    def test_latest_exact732(self):
        changes = p.baseline_contract(self.old, self.new, self.state, self.manifest)
        self.assertEqual(sum(c['gain'] for c in changes), 2)
        self.assertTrue(all('i_payload_buffer' not in c['scope'] for c in changes))

    def test_exact_targets_and_full_complement(self):
        self.assertEqual(len(self.candidates), 1792)
        self.assertEqual(len(self.guards), 41214)
        self.assertTrue(all(not c['hit_before'] for c in self.candidates))
        for scope in self.scopes.values():
            target = int(scope['target_raw_bitmap'], 16)
            guard = int(scope['protected_raw_bitmap'], 16)
            self.assertEqual(bin(target).count('1'), 896)
            self.assertEqual(bin(guard).count('1'), 20607)
            self.assertEqual(target & guard, 0)
            self.assertEqual(target | guard, (1 << 21503)-1)

    def test_mask_plane_offset_byte_valid_preserved(self):
        self.assertTrue(all(int(c['point']['line']) in (375,378,401,403) for c in self.candidates))
        for line in (91,97,219,223,261,262,282,285,288,340,342,346,349):
            self.assertTrue(any(int(g['point']['line']) == line for g in self.guards), line)

    def test_complete_group_neighbors(self):
        self.assertEqual(len(self.groups), 1344)
        self.assertEqual(sum(len(g['targets']) for g in self.groups), 1792)
        self.assertEqual(sum(len(g['retained']) for g in self.groups), 1792)
        self.assertTrue(all(g['retained'] for g in self.groups))

    def test_real_source_contract(self):
        self.assertEqual(set(p.source_contract(**self.texts)), {'weight','activation'})

    def source_negative(self, name, old, new):
        texts = dict(self.texts)
        self.assertEqual(texts[name].count(old), 1, 'Exactly one faithful source mutation required')
        texts[name] = texts[name].replace(old, new, 1)
        with self.assertRaises(ValueError):
            p.source_contract(**texts)

    def test_side_consumption_mutation(self):
        self.source_negative('payload', 'weight_location[B].plane == 2)', 'weight_location[B].plane == 1)')

    def test_pending_strb_direct_ingress_mutation(self):
        self.source_negative('adapter', 'weight_pending_q.strb <= weight_remaining[31:16];',
                             'weight_pending_q.strb <= weight_mask[31:16];')

    def test_registered_capture_guard_mutation(self):
        self.source_negative('adapter', 'if (weight_source_valid[1] && (|weight_remaining[31:16])) begin',
                             'if (weight_source_valid[0] && (|weight_remaining[31:16])) begin')

    def test_oldmask_gate_mutation(self):
        self.source_negative('adapter', 'weight_pending_target_q[b].valid && weight_pending_q.strb[b],',
                             'weight_pending_target_q[b].valid,')

    def test_stream_parameter_mutation(self):
        self.source_negative('adapter', ".StreamWriteData(1'b1)", ".StreamWriteData(1'b0)")

    def test_ungated_ternary_mutation(self):
        self.source_negative('payload', 'if (enable) weight_side_q[row][b]',
                             'if (use_newer || 1\'b1) weight_side_q[row][b]')

    def test_alternate_storage_writer(self):
        texts = dict(self.texts)
        texts['adapter'] += '\nassign weight_pending_q.strb = 16\'hffff;\n'
        with self.assertRaises(ValueError):
            p.source_contract(**texts)

    def test_all_bit_induction_transitions(self):
        count = 0
        for mask, side in ((False,False),(True,False),(False,True)):
            for flags in itertools.product((False,True), repeat=8):
                reset, clear, accept, incoming_mask, incoming_side, remaining, drain, consumed = flags
                m,s = p.pending_bit(mask,side,reset=reset,clear=clear,accept=accept,
                    incoming_mask=incoming_mask,incoming_side=incoming_side,global_remaining=remaining,
                    drain=drain,consumed=consumed)
                self.assertFalse(m and s)
                count += 1
        self.assertEqual(count,768)

    def test_clear_preserves_metadata_not_fake_reset(self):
        self.assertEqual(p.pending_bit(True,False,clear=True), (True,False))
        self.assertEqual(p.pending_bit(False,True,clear=True), (False,True))

    def test_illegal_pending_side_rejected(self):
        with self.assertRaises(ValueError):
            p.pending_bit(True,True)

    def test_reset_clears_only_strb(self):
        self.assertEqual(p.pending_bit(True,True,reset=True), (False,True))
        self.assertEqual(p.induction_check()['transition_combinations_checked'],768)

    def test_induction_mutant_not_consuming_side_rejected(self):
        def mutant(mask,side,**kwargs):
            if kwargs.get('accept') and kwargs.get('global_remaining') and not kwargs.get('reset') and not kwargs.get('clear'):
                return kwargs['incoming_mask'],kwargs['incoming_side']
            return p.pending_bit(mask,side,**kwargs)
        with self.assertRaises(ValueError):
            p.induction_check(mutant)

    def test_actual_evidence_runs_induction(self):
        with patch.object(p,'induction_check',wraps=p.induction_check) as gate:
            actual=p.evidence()
        gate.assert_called_once_with()
        self.assertEqual(actual['boolean_induction']['transition_combinations_checked'],768)
        self.assertEqual(actual['boolean_induction']['reset_base_states_checked'],4)
        self.assertEqual(actual['boolean_induction']['actual_DUT_cases'],0)
        self.assertFalse(actual['native_qualified'])

    def test_target_table_wrong_source_rejected(self):
        point = copy.deepcopy(self.candidates[0]['point']); point['file_id'] = '1'
        with self.assertRaises(ValueError):
            p.target_class(point)

    def test_foreign_dynamic_group_rejected(self):
        rows = list(self.candidates); rows[0] = next(g for g in self.guards if g['point']['line'] == '282')
        with self.assertRaises(ValueError):
            p.groups(rows,self.guards)

    def test_missing_target_rejected(self):
        with self.assertRaises(ValueError):
            p.groups(self.candidates[1:],self.guards)

    def test_duplicate_target_rejected(self):
        with self.assertRaises(ValueError):
            p.groups([self.candidates[0]]+self.candidates[:-1],self.guards)

    def test_parent_pin_drift_rejected(self):
        with patch.object(p,'PARENT_SHA','a'*64):
            with self.assertRaises(ValueError):
                p.evidence()

    def test_changed_payload_latest_rejected(self):
        latest = copy.deepcopy(self.new)
        scope = self.candidates[0]['scope']
        row = latest['metrics']['cond'][scope]
        row['bits'] = hex(int(row['bits'],16) | (1 << (21502-self.candidates[0]['point']['raw_index'])))
        with self.assertRaises(ValueError):
            p.inventory(p.compiled.Design(p.DESIGN),self.old,latest,self.original)

    def test_wrong_baseline_prefix_rejected(self):
        latest = dict(self.new,tests=list(reversed(self.new['tests'])))
        with self.assertRaises(ValueError):
            p.baseline_contract(self.old,latest,self.state,self.manifest)

    def native_records(self):
        # Host fixtures deliberately use IDs unrelated to compiled cond IDs/raw rows.
        ids = {(g['scope'],g['expression']):str(90000+i) for i,g in enumerate(self.groups)}
        records = []
        for i,c in enumerate(self.candidates):
            point = c['point']
            records.append(dict(scope=c['scope'], expression=point['expression'], vector=point['vector'],
                module_checksum=c['module_checksum'], metric_checksum=c['checksum'],
                native_id=ids[c['scope'],point['expression']], point_checksum=point['attributes']['chksum'],
                width=point['attributes']['width'],bit='-1',vector_id=str(70000+i)))
        return records

    def test_observed_identity_not_compiled_guess(self):
        p.native.bind(self.native_records(), self.candidates)

    def mutate_native(self, field, value):
        records = self.native_records(); records[0][field] = value
        with self.assertRaises(ValueError):
            p.native.bind(records,self.candidates)

    def test_wrong_scope(self): self.mutate_native('scope','dut.other')
    def test_wrong_checksum(self): self.mutate_native('point_checksum','1')
    def test_wrong_width(self): self.mutate_native('width','8')
    def test_wrong_expression(self): self.mutate_native('expression','dynamic_plane_predicate')
    def test_wrong_vector(self): self.mutate_native('vector','111111')
    def test_wrong_module(self): self.mutate_native('module_checksum','1')

    def test_native_alias(self):
        records = self.native_records()
        records[1]['native_id'] = records[0]['native_id']
        self.assertNotEqual(records[0]['expression'], records[1]['expression'])
        with self.assertRaises(ValueError):
            p.native.bind(records,self.candidates)

    def test_native_missing_extra(self):
        records = self.native_records()
        for bad in (records[:-1], records + records[:1]):
            with self.assertRaises(ValueError):
                p.native.bind(bad,self.candidates)

    def test_real_native_grammar_fixture_only(self):
        self.assertEqual(len(p.native.parse_records(p.FIXTURE.read_bytes().decode('ascii'))),24)

    def test_whole_instance_and_other_metric_rejected(self):
        for raw in ('CHECKSUM: "1 2"\nINSTANCE: dut\n',
                    'CHECKSUM: "1 2"\nINSTANCE: dut\nToggle 1\n'):
            with self.assertRaises(ValueError):
                p.native.parse_records(raw)

    def test_existing_artifact_protected(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'proof.json';path.write_text('{}')
            with self.assertRaises(ValueError):
                p.verify(path,'a'*64)


if __name__ == '__main__':
    unittest.main()
