import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_scalar_entropy788 as a


class Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = a.life.read_bound(a.QUAL/'qualification.json',a.Q_SHA)
        cls.docs = {Path(p).name:a.life.read_bound(Path(p),h) for p,h in cls.q['output_pins'].items()
                    if p.endswith('.json')}
        cls.old = json.loads((a.run.BASE/'combined-bits.json').read_bytes())

    def baseline(self):
        before = copy.deepcopy(self.old)
        before['tests'].append('/synthetic/csr787/code.vdb')
        return before

    def test_real_parent_sealed_architecture(self):
        a.architecture(self.q,self.docs)

    def test_architecture_counters_and_unknown_gain_not_relaxed(self):
        for key,value in (('baseline',787),('architecture_pass',False),('MDA_direction_gain_qualified',True)):
            q = copy.deepcopy(self.q)
            q[key] = value
            with self.subTest(key=key),self.assertRaises(ValueError):
                a.architecture(q,self.docs)
        for name,key,value in (('native-frame.json','checks',389),
                               ('ELF-native-initialization.json','native_first_read_store_dominance',False)):
            docs = copy.deepcopy(self.docs)
            docs[name][key] = value
            with self.subTest(name=name),self.assertRaises(ValueError):
                a.architecture(self.q,docs)

    def test_scalar_skip_rejected(self):
        docs = copy.deepcopy(self.docs)
        docs['scalar-comparison.json']['skipped_unobservable_register_values'] = 1
        with self.assertRaises(ValueError):
            a.architecture(self.q,docs)

    def test_target_Toggle_gain_cannot_be_invented(self):
        docs = copy.deepcopy(self.docs)
        docs['typed-toggle.json']['new_serialized_positions'][a.run.SCOPES[0]] = [0]
        with self.assertRaises(ValueError):
            a.architecture(self.q,docs)

    def test_actual_singleton_full6162_OR_on787_prefix(self):
        before = self.baseline()
        after,delta = a.full_union(before,self.docs['single-bits.json'])
        self.assertEqual(after['tests'],before['tests']+[str(a.RUN/'code.vdb')])
        self.assertEqual(delta['metrics'],dict(line=0,cond=7,branch=0,fsm=0))
        self.assertEqual(sum(len(v) for v in after['metrics'].values()),6162)

    def test_787_overlap_rebases_fresh_gain(self):
        before = self.baseline()
        old = before['metrics']['cond'][a.GAIN_SCOPE]
        new = self.docs['single-bits.json']['metrics']['cond'][a.GAIN_SCOPE]
        fresh = int(new['bits'],16)&~int(old['bits'],16)
        old['bits'] = hex(int(old['bits'],16)|(fresh&-fresh))
        _,delta = a.full_union(before,self.docs['single-bits.json'])
        self.assertEqual(delta['metrics']['cond'],6)

    def test_zero_gain_rejected(self):
        before = self.baseline()
        before['metrics']['cond'][a.GAIN_SCOPE] = copy.deepcopy(self.docs['single-bits.json']['metrics']['cond'][a.GAIN_SCOPE])
        with self.assertRaises(ValueError):
            a.full_union(before,self.docs['single-bits.json'])

    def test_wrong_baseline_or_duplicate_VDB(self):
        for before in (copy.deepcopy(self.old),self.baseline()):
            if len(before['tests']) == 787:
                before['tests'][-1] = str(a.RUN/'code.vdb')
            with self.assertRaises(ValueError):
                a.full_union(before,self.docs['single-bits.json'])

    def test_compiled_shape_checksum_and_missing_scope_rejected(self):
        for kind in ('checksum','missing'):
            single = copy.deepcopy(self.docs['single-bits.json'])
            if kind == 'checksum':
                single['metrics']['cond'][a.GAIN_SCOPE]['checksum'] = '0'
            else:
                single['metrics']['cond'].pop(a.GAIN_SCOPE)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                a.full_union(self.baseline(),single)

    def test_differing_design_or_input_pin_rejected(self):
        for kind in ('design','pin'):
            single = copy.deepcopy(self.docs['single-bits.json'])
            if kind == 'design':
                single['design']['foreign.xml'] = '0'*64
            else:
                p = next(iter(self.old['input_hashes']))
                single['input_hashes'][p] = '0'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                a.full_union(self.baseline(),single)

    def test_ledger_retention_and_exact_status(self):
        before = self.baseline()
        original = [str(a.life.IMAGE)+'.vdb',*self.old['tests']]
        ledger = [str(a.life.IMAGE)+'.vdb',*before['tests']]
        status = dict(aggregate_passed=787,coverage_admitted=True)
        a.ledger_gate(ledger,before,status,original)
        for bad in (dict(status,aggregate_passed=786),dict(status,coverage_admitted=False)):
            with self.assertRaises(ValueError):
                a.ledger_gate(ledger,before,bad,original)
        swapped = ledger.copy()
        swapped[1],swapped[2] = swapped[2],swapped[1]
        with self.assertRaises(ValueError):
            a.ledger_gate(swapped,before,status,original)

    def test_dedup_uses_only_historical_authority(self):
        ledger = ['/design']+['/test%d/code.vdb'%i for i in range(787)]
        elf = dict(ledger_members=787,duplicate=False,members=[dict(vdb=p) for p in ledger[1:]],
                   pins={'/old/command.json':'a'*64})
        a.historical_elf_gate(elf,ledger,{'/old/command.json':'a'*64})
        for bad in (dict(elf,duplicate=True),dict(elf,pins={'/candidate/command.json':'b'*64})):
            with self.assertRaises(ValueError):
                a.historical_elf_gate(bad,ledger,{'/old/command.json':'a'*64})

    def test_unadmitted_baseline_fails_before_output(self):
        with patch.object(a.life,'read_bound',return_value=dict(coverage_admitted=False)):
            with self.assertRaises(ValueError):
                a.evaluate(a.BASE,'0'*64)

    def test_agent_or_other787_branch_rejected_before_read(self):
        with patch.object(a.life,'read_bound') as read:
            with self.assertRaises(ValueError):
                a.evaluate(a.run.OUT/'csr-satp-sepc-offline-admitted787-agent-20261008-01','0'*64)
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
