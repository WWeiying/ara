import copy
import json
import unittest
from unittest.mock import patch

import admit_csr_satp_sepc787 as p


class JointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = p.life.read_bound(p.QUAL / 'qualification.json', p.QUAL_SHA)
        cls.c = p.life.read_bound(p.QUAL / 'packed-epoch-closure.json', p.CLOSURE_SHA)

    def test_actual_complete_joint_authority(self):
        p.joint_gate(self.q, self.c, p.QUAL_SHA)

    def test_hold_core_rejected(self):
        q = copy.deepcopy(self.q); q['status'] = 'QUALIFICATION_HOLD_NOT_ADMITTED'
        with self.assertRaises(ValueError): p.joint_gate(q, self.c, p.QUAL_SHA)

    def test_missing_owner_count_rejected(self):
        q = copy.deepcopy(self.q); q['native_CSR_owners'] = 29
        with self.assertRaises(ValueError): p.joint_gate(q, self.c, p.QUAL_SHA)

    def test_bool_count_rejected(self):
        q = copy.deepcopy(self.q); q['checks'] = True
        with self.assertRaises(ValueError): p.joint_gate(q, self.c, p.QUAL_SHA)

    def test_missing_memory_evidence_rejected(self):
        q = copy.deepcopy(self.q); q['output_pins'].pop(str(p.QUAL/'architecture-audit.json'))
        with self.assertRaises(ValueError): p.joint_gate(q, self.c, p.QUAL_SHA)

    def test_wrong_core_closure_binding_rejected(self):
        c = copy.deepcopy(self.c); c['core_sha256'] = '0'*64
        with self.assertRaises(ValueError): p.joint_gate(self.q, c, p.QUAL_SHA)

    def test_wrong_cycle_plan_binding_rejected(self):
        c = copy.deepcopy(self.c); c['input_pins'][str(p.PLAN)] = '0'*64
        with self.assertRaises(ValueError): p.joint_gate(self.q, c, p.QUAL_SHA)

    def test_unreviewed_seals_rejected_before_consumption(self):
        with self.assertRaisesRegex(ValueError, 'parent-reviewed'): p.evaluate('0'*64, p.CLOSURE_SHA)


class UnionTests(unittest.TestCase):
    def fixtures(self):
        def metrics(bits): return {m: {'scope%d'%i: dict(width=2, checksum='1', bits=bits)
                                     for i in range(count)} for m, count in p.COUNTS.items()}
        before = dict(design={'shape': 'same'}, tests=['historical%d'%i for i in range(786)],
                      input_hashes={'/fixture/old': 'a'*64}, metrics=metrics('0x2'))
        single = dict(design=before['design'], tests=[str(p.consumer.adapter.packed.RUN/'code.vdb')],
                      input_hashes={'/fixture/new': 'b'*64}, metrics=metrics('0x1'))
        return before, single

    def test_all6162_exact_or_prefix(self):
        old, single = self.fixtures(); after = p.full_union(old, single)
        self.assertEqual(after['tests'], old['tests'] + single['tests'])
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)
        self.assertTrue(all(row['bits'] == '0x3' for rows in after['metrics'].values() for row in rows.values()))

    def test_duplicate_candidate_rejected(self):
        old, single = self.fixtures(); old['tests'][-1] = single['tests'][0]
        with self.assertRaises(ValueError): p.full_union(old, single)

    def test_missing_instance_rejected(self):
        old, single = self.fixtures(); single['metrics']['line'].pop('scope0')
        with self.assertRaises(ValueError): p.full_union(old, single)

    def test_checksum_mutation_rejected(self):
        old, single = self.fixtures(); single['metrics']['cond']['scope0']['checksum'] = '2'
        with self.assertRaises(ValueError): p.full_union(old, single)

    def test_bool_width_rejected(self):
        old, single = self.fixtures(); old['metrics']['branch']['scope0']['width'] = True
        single['metrics']['branch']['scope0']['width'] = True
        with self.assertRaises(ValueError): p.full_union(old, single)

    def test_out_of_bounds_bits_rejected(self):
        old, single = self.fixtures(); single['metrics']['fsm']['scope0']['bits'] = '0x4'
        with self.assertRaises(ValueError): p.full_union(old, single)

    def test_zero_gain_rejected_toggle_only_positive_allowed(self):
        delta = dict(metrics={m: 0 for m in p.COUNTS})
        with self.assertRaisesRegex(ValueError, 'Zero-gain'): p.positive(delta, [dict(gained=[])])
        p.positive(delta, [dict(gained=[1, 2])])


class DedupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = p.life.read_bound(p.BASE/'admission-manifest.json', p.BASE_SHA)
        cls.authority = p.life.merge_pins(cls.base['input_pins'], cls.base['output_pins'])
        cls.ledger = (p.BASE/'combined-inputs.txt').read_text().splitlines()

    def test_actual_all786_historical_ELF_owners(self):
        self.assertEqual(p.historical_dedup(self.base, self.ledger, self.authority)['ledger_members'], 786)

    def test_duplicate_last_actual_ELF_rejected(self):
        path = p.Path(self.ledger[-1]).parent/'manifest.json'
        command = p.life.read_bound(path, self.authority[str(path)])['command']
        elf = next(x.split('=', 1)[1] for x in command if x.startswith('+PRELOAD='))
        with patch.object(p.f.runner, 'ELF_SHA', self.authority[elf]):
            with self.assertRaisesRegex(ValueError, 'duplicate/owner'):
                p.historical_dedup(self.base, self.ledger, self.authority)


if __name__ == '__main__': unittest.main()
