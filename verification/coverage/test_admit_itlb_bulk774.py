import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import admit_itlb_bulk774 as a


class ActualGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=json.loads((a.QUAL/'qualification.json').read_text())
        cls.docs={name:json.loads((a.QUAL/name).read_text()) for name in a.DOCS}
        cls.before=json.loads((a.BASE/'combined-bits.json').read_text())
        cls.single=cls.docs['single-bits.json']

    def load_mutated(self, mutation):
        q=copy.deepcopy(self.q);docs=copy.deepcopy(self.docs)
        mutation(q,docs)
        def read(path,seal):
            return q if path.name=='qualification.json' else docs[path.name]
        with patch.object(a.life,'read_bound',side_effect=read),patch.object(a.life,'check'):
            with self.assertRaises(ValueError):a.documents(a.QUAL,a.QUAL_SHA)

    def test_actual_complete_qualification(self):
        q,docs=a.documents(a.QUAL,a.QUAL_SHA)
        self.assertEqual(q,self.q);self.assertEqual(docs,self.docs)

    def test_actual_parent_complete_semantic_replay(self):
        q,d=a.documents(a.QUAL,a.QUAL_SHA)
        p,pd=a.documents(a.REPLAY,a.REPLAY_SHA)
        a.replay_equal(q,d,p,pd)

    def test_failure_and_zero_gain_rejected(self):
        for field,value in (('status','FAILED'),('toggle_new_positions',0),('target_new_positions',861),
                            ('coverage_admitted',True)):
            self.load_mutated(lambda q,d:q.update({field:value}))

    def test_skip_or_scalar_mismatch_rejected(self):
        for field,value in (('mismatch',{}),('skipped_unobservable_register_values',1),
                            ('matched_scalar_writes',66599),('ara_trap_events',47)):
            self.load_mutated(lambda q,d:d['scalar-comparison.json'].update({field:value}))

    def test_missing_code_guard_rejected(self):
        self.load_mutated(lambda q,d:d['code-write-dominance.json'].update(word_reads=8191))

    def test_missing_slot_or_axi_rejected(self):
        self.load_mutated(lambda q,d:d['itlb-axi-observations.json']['entry_visits'][2].pop())
        self.load_mutated(lambda q,d:d['itlb-axi-observations.json']['AXI_channels'].update(b=18151))

    def test_consumer_before_response_rejected(self):
        self.load_mutated(lambda q,d:d['csr-lifecycle.json']['records'][0].update(consumer_cycle=0))

    def test_extra_trap_rejected(self):
        self.load_mutated(lambda q,d:d['native-oracle.json']['traps'].append({}))

    def test_pin_check_failure_propagates(self):
        with patch.object(a.life,'check',side_effect=ValueError('pin drift')):
            with self.assertRaisesRegex(ValueError,'pin drift'):a.documents(a.QUAL,a.QUAL_SHA)

    def test_parent_semantic_mutation_rejected(self):
        bad=copy.deepcopy(self.docs);bad['csr-lifecycle.json']['records'][0]['word'] ^= 1
        with self.assertRaises(ValueError):a.replay_equal(self.q,self.docs,self.q,bad)

    def test_actual_full6162_or(self):
        after=a.union(self.before,self.single)
        self.assertEqual(after,self.docs['diagnostic-combined-bits.json'])
        self.assertEqual(len(after['tests']),774)

    def test_wrong_baseline_duplicate_or_foreign_vdb_rejected(self):
        for kind in ('short','duplicate','foreign'):
            before=copy.deepcopy(self.before);single=copy.deepcopy(self.single)
            if kind=='short':before['tests'].pop()
            elif kind=='duplicate':before['tests'][-1]=single['tests'][0]
            else:single['tests']=['/foreign/code.vdb']
            with self.assertRaises(ValueError):a.union(before,single)

    def test_design_checksum_width_and_scope_mismatch_rejected(self):
        for kind in ('design','checksum','width','scope'):
            single=copy.deepcopy(self.single)
            metric=next(iter(single['metrics']));scope=next(iter(single['metrics'][metric]))
            if kind=='design':single['design']['foreign']='bad'
            elif kind=='scope':single['metrics'][metric].pop(scope)
            elif kind=='checksum':single['metrics'][metric][scope]['checksum']='bad'
            else:single['metrics'][metric][scope]['width']+=1
            with self.assertRaises(ValueError):a.union(self.before,single)

    def test_independent_or_detects_combine_bug(self):
        with patch.object(a.core.bitmap,'combine',return_value=self.before):
            with self.assertRaises(ValueError):a.union(self.before,self.single)

    def test_duplicate_elf_rejected(self):
        with tempfile.TemporaryDirectory(dir=a.life.OUT) as tmp:
            p=Path(tmp)/'input.elf';p.write_bytes(b'\x7fELFduplicate')
            with self.assertRaisesRegex(ValueError,'Duplicate historical ELF'):
                a.dedup(['/design',str(Path(tmp)/'code.vdb')],a.life.digest(p))

    def test_separate_admission_authorization(self):
        with patch('sys.argv',['admit','admit','--output',str(a.life.OUT/'unused')]),\
             patch.object(a,'evaluate',side_effect=AssertionError('must not evaluate')):
            with self.assertRaisesRegex(ValueError,'authorization'):a.main()


if __name__=='__main__':unittest.main()
