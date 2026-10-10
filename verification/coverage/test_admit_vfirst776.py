"""Sealed real qualification/775 OR fixtures and narrow admission negatives; no EDA."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_vfirst776 as a


class UnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = a.life.read_bound(a.runner.BASE / 'admission-manifest.json', a.runner.BASE_SHA)
        path = a.runner.BASE / 'combined-bits.json'
        cls.before = a.life.read_bound(path, base['output_pins'][str(path)])
        q = a.life.read_bound(a.QUAL, a.QUAL_SHA)
        path = a.QUAL.parent / 'single-bits.json'
        cls.single = a.life.read_bound(path, q['input_pins'][str(path)])

    def test_real_full6162_OR_and775_prefix(self):
        after = a.full_union(self.before, self.single)
        self.assertEqual(after['tests'][:775], self.before['tests'])
        self.assertEqual(after['tests'][775:], [str(a.RUN / 'code.vdb')])
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)

    def test_prefix_member_dropped(self):
        before = copy.deepcopy(self.before); before['tests'].pop()
        with self.assertRaises(ValueError): a.full_union(before, self.single)

    def test_duplicate_candidate(self):
        before = copy.deepcopy(self.before); before['tests'][-1] = str(a.RUN / 'code.vdb')
        with self.assertRaises(ValueError): a.full_union(before, self.single)

    def test_foreign_candidate(self):
        single = copy.deepcopy(self.single); single['tests'] = ['/foreign/code.vdb']
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_missing_scope(self):
        single = copy.deepcopy(self.single); single['metrics']['line'].pop(next(iter(single['metrics']['line'])))
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_extra_scope(self):
        single = copy.deepcopy(self.single); single['metrics']['line']['foreign'] = dict(width=0, checksum='0', bits='0x0')
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_width_drift(self):
        single = copy.deepcopy(self.single); next(iter(single['metrics']['line'].values()))['width'] += 1
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_checksum_drift(self):
        single = copy.deepcopy(self.single); next(iter(single['metrics']['line'].values()))['checksum'] = 'foreign'
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_design_drift(self):
        single = copy.deepcopy(self.single); single['design'] = {}
        with self.assertRaises(ValueError): a.full_union(self.before, single)


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = a.life.read_bound(a.QUAL, a.QUAL_SHA)
        cls.parent = a.life.read_bound(a.REPLAY, a.REPLAY_SHA)
        cls.pre = a.runner.preflight(); cls.reference = a.case.reference_prefix(cls.pre)

    def check(self, q):
        with patch.object(a.case, 'reference_prefix', return_value=self.reference): a.architecture(q, self.pre)

    def test_real_qualified_contract(self): self.check(self.q)

    def test_real_independent_parent_contract_and_semantic_equality(self):
        self.check(self.parent); a.replay_equal(self.q, self.parent)

    def test_parent_difference_rejected(self):
        parent = copy.deepcopy(self.parent); parent['signature']['checks'] -= 1
        with self.assertRaises(ValueError): a.replay_equal(self.q, parent)

    def test_wrong_signature(self):
        q = copy.deepcopy(self.q); q['signature']['required_read_bytes'] -= 8
        with self.assertRaises(ValueError): self.check(q)

    def test_scalar_skip(self):
        q = copy.deepcopy(self.q); q['scalar']['skipped_unobservable_register_values'] = 1
        with self.assertRaises(ValueError): self.check(q)

    def test_scalar_retirement_drop(self):
        q = copy.deepcopy(self.q); q['scalar']['matched_instructions'] -= 1
        with self.assertRaises(ValueError): self.check(q)

    def test_native_skip(self):
        q = copy.deepcopy(self.q); q['native']['skipped_bytes'] = 1
        with self.assertRaises(ValueError): self.check(q)

    def test_vfirst_missing_backend(self):
        q = copy.deepcopy(self.q); q['native']['vfirst_without_VRF_write'] -= 1
        with self.assertRaises(ValueError): self.check(q)

    def test_vlm_missing_byte(self):
        q = copy.deepcopy(self.q); q['native']['native_mask_writers'][0]['compared_bytes'] -= 1
        with self.assertRaises(ValueError): self.check(q)

    def test_wrong_native_owner(self):
        q = copy.deepcopy(self.q); q['native']['native_mask_writers'][0]['arch_seq'] += 1
        with self.assertRaises(ValueError): self.check(q)

    def test_no_SID_owner_proof(self):
        q = copy.deepcopy(self.q); q['lifecycle']['exact_SID_owner_checked'] = False
        with self.assertRaises(ValueError): self.check(q)

    def test_timeout_not_qualification(self):
        q = copy.deepcopy(self.q); q['terminal']['timeout'] = True
        with self.assertRaises(ValueError): self.check(q)

    def test_bool_returncode_not_zero_receipt(self):
        q = copy.deepcopy(self.q); q['terminal']['returncode'] = False
        with self.assertRaises(ValueError): self.check(q)

    def test_foreign_ELF_pin(self):
        q = copy.deepcopy(self.q); q['input_pins'][str(a.runner.ELF)] = '0' * 64
        with self.assertRaises(ValueError): self.check(q)


class HistoricalTests(unittest.TestCase):
    def fixture(self):
        ledger = ['compile'] + ['vdb%d' % i for i in range(775)]
        audit = dict(ledger_members=775, duplicate=False, pins={'old.elf': 'sealed'},
                     members=[dict(vdb=p) for p in ledger[1:]])
        return ledger, audit

    def test_baseline_only_authority(self):
        ledger, audit = self.fixture()
        with patch.object(a, 'dedup', return_value=audit) as function:
            self.assertEqual(a.historical(ledger, {'old.elf': 'sealed'})['baseline'], 775)
            self.assertEqual(function.call_args.args[1:], (a.runner.ELF_SHA, {'old.elf': 'sealed'}))

    def test_candidate_cannot_bless_missing_history(self):
        ledger, audit = self.fixture()
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, {})

    def test_drifted_history(self):
        ledger, audit = self.fixture()
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, {'old.elf': 'foreign'})

    def test_history_member_drop(self):
        ledger, audit = self.fixture(); audit['members'].pop()
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, {'old.elf': 'sealed'})

    def test_duplicate_historical_ELF(self):
        ledger, audit = self.fixture(); audit['duplicate'] = True
        with patch.object(a, 'dedup', return_value=audit):
                with self.assertRaises(ValueError): a.historical(ledger, {'old.elf': 'sealed'})


class NativeContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = a.life.read_bound(a.QUAL, a.QUAL_SHA); cls.pre = a.runner.preflight()
        cls.reference = a.case.reference_prefix(cls.pre)
        for name in ('commit_trace.csv', 'vector_trace.csv'):
            path = a.RUN / name
            a.require(a.life.digest(path) == cls.q['input_pins'][str(path)], 'Actual fixture trace pin')
        lanes, vlen, cls.activities = a.case.vc._parse_vector_trace(a.RUN / 'vector_trace.csv')
        starts, retires, rejected = a.case.vc._parse_architecture_mapping(a.RUN / 'commit_trace.csv')
        cls.mapping = a.case.vc._map_spike_commits(
            a.case.vc._map_architecture_retires(starts, retires, rejected), cls.reference)

    def check(self, activities=None, mapping=None):
        return a.context_gate(self.activities if activities is None else activities,
            self.mapping if mapping is None else mapping, self.reference, self.pre['symbols'])

    def reject_context(self, field, value):
        activities = copy.deepcopy(self.activities); setattr(activities[5], field, value)
        with self.assertRaises(ValueError): self.check(activities)

    def test_actual_eight_native_contexts(self):
        proof = self.check()
        self.assertEqual([r['arch_seq'] for r in proof['records']], list(range(5, 76, 10)))
        self.assertTrue(all(r['vl'] == 1024 and r['VRF_writes'] == 0 for r in proof['records']))

    def test_wrong_VL(self): self.reject_context('vl', 128)
    def test_wrong_vstart(self): self.reject_context('vstart', 1)
    def test_wrong_EEW(self): self.reject_context('eew', 1)
    def test_wrong_use_vd(self): self.reject_context('use_vd', True)
    def test_wrong_opcode_identity(self): self.reject_context('instruction', 0)
    def test_incomplete_allocation(self): self.reject_context('completions', 0)

    def test_wrong_PC_mapping(self):
        mapping = dict(self.mapping); mapping[5] = 0
        with self.assertRaises(ValueError): self.check(mapping=mapping)

    def test_missing_native_context(self):
        activities = dict(self.activities); activities.pop(5)
        with self.assertRaises(ValueError): self.check(activities)

    def test_vfirst_VRF_writer(self):
        activities = copy.deepcopy(self.activities)
        activities[5].writes = activities[3].writes[:1]
        with self.assertRaises(ValueError): self.check(activities)


class RealEvaluationTest(unittest.TestCase):
    def test_actual_evaluate_no_admission_or_EDA(self):
        # Execute every real dependency/receipt/historical dedup and OR gate without output creation.
        products, text = a.evaluate()
        self.assertEqual(len(text.splitlines()), 777)
        self.assertEqual(products['status.json']['aggregate_passed'], 776)
        self.assertEqual(products['vfirst-toggle-gain775.json']['target_hit_count'], 20)
        self.assertEqual(products['elf-ledger-dedup.json']['ledger_members'], 775)
        self.assertFalse(products['elf-ledger-dedup.json']['duplicate'])
        self.assertTrue(products['status.json']['historical_fixed_image_only'])
        self.assertFalse(products['status.json']['official_percentage_claimed'])
        self.assertEqual(products['vfirst-native-context.json']['requests'], 8)


if __name__ == '__main__': unittest.main()
