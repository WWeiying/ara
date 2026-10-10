import copy
import json
from unittest.mock import patch
import unittest
import admit_vmacc_c_fifo775 as a


class UnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((a.case.p.old.BASE/'combined-bits.json').read_bytes())
        cls.before['tests'].append(str(a.itlb.RUN/'code.vdb'))
        cls.single = json.loads((a.AGENT.parent/'single-bits.json').read_bytes())

    def test_all6162_OR_and774_prefix(self):
        after = a.full_union(self.before, self.single)
        self.assertEqual(after['tests'][:774], self.before['tests'])
        self.assertEqual(len(after['tests']), 775)
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)

    def test_ITLB_member_drop(self):
        before = copy.deepcopy(self.before); before['tests'].pop()
        with self.assertRaises(ValueError): a.full_union(before, self.single)

    def test_duplicate_candidate(self):
        before = copy.deepcopy(self.before); before['tests'][-1] = str(a.RUN/'code.vdb')
        with self.assertRaises(ValueError): a.full_union(before, self.single)

    def test_scope_drop(self):
        single = copy.deepcopy(self.single); single['metrics']['line'].pop(next(iter(single['metrics']['line'])))
        with self.assertRaises((ValueError, KeyError)): a.full_union(self.before, single)

    def test_shape_drift(self):
        single = copy.deepcopy(self.single)
        next(iter(single['metrics']['line'].values()))['width'] += 1
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_checksum_drift(self):
        single = copy.deepcopy(self.single)
        next(iter(single['metrics']['line'].values()))['checksum'] = 'wrong'
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_design_drift(self):
        single = copy.deepcopy(self.single); single['design'] = {}
        with self.assertRaises(ValueError): a.full_union(self.before, single)

    def test_candidate_identity(self):
        single = copy.deepcopy(self.single); single['tests'] = ['/other/code.vdb']
        with self.assertRaises(ValueError): a.full_union(self.before, single)


class HistoricalTests(unittest.TestCase):
    def fixture(self):
        ledger = ['compile'] + ['test%d' % n for n in range(774)]
        audit = dict(ledger_members=774, duplicate=False, pins={'old.elf':'hash'},
            members=[dict(vdb=p) for p in ledger[1:]])
        return ledger, audit

    def test_exact_historical_authority(self):
        ledger, audit = self.fixture()
        with patch.object(a, 'dedup', return_value=audit) as d:
            self.assertEqual(a.historical(ledger, 'new', {'old.elf':'hash'})['baseline'], 774)
            self.assertEqual(d.call_args.args[2], {'old.elf':'hash'})

    def test_candidate_receipt_cannot_supply_missing_history(self):
        ledger, audit = self.fixture()
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, 'new', {})

    def test_history_pin_drift(self):
        ledger, audit = self.fixture()
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, 'new', {'old.elf':'different'})

    def test_history_member_drop(self):
        ledger, audit = self.fixture(); audit['members'].pop()
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, 'new', {'old.elf':'hash'})

    def test_duplicate_ELF(self):
        ledger, audit = self.fixture(); audit['duplicate'] = True
        with patch.object(a, 'dedup', return_value=audit):
            with self.assertRaises(ValueError): a.historical(ledger, 'new', {'old.elf':'hash'})


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = json.loads(a.AGENT.read_bytes())
        cls.pre = a.case.runner.preflight()

    def check(self, q):
        with patch.object(a.case.runner, 'preflight', return_value=self.pre): a.architecture(q)

    def test_real_completed_architecture(self): self.check(self.q)

    def test_signature_corrupt(self):
        q = copy.deepcopy(self.q); q['signature']['checks'] -= 1
        with self.assertRaises(ValueError): self.check(q)

    def test_unknown_vector(self):
        q = copy.deepcopy(self.q); q['vector']['skipped_unknown_bytes'] = 1
        with self.assertRaises(ValueError): self.check(q)

    def test_lifecycle_owner_gate(self):
        q = copy.deepcopy(self.q); q['lifecycle']['exact_SID_owner_checked'] = False
        with self.assertRaises(ValueError): self.check(q)

    def test_wrong_native_vl_sequence(self):
        q = copy.deepcopy(self.q); q['native']['allocations'][4]['vl'] = 1024
        with self.assertRaises(ValueError): self.check(q)

    def test_incomplete_scalar(self):
        q = copy.deepcopy(self.q); q['scalar']['matched_instructions'] -= 1
        with self.assertRaises(ValueError): self.check(q)


if __name__ == '__main__': unittest.main()
