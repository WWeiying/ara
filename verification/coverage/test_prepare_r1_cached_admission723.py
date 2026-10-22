"""Actual sealed terminal/base/proposal primitives; no repeated full replay inside rejection tests."""
from copy import deepcopy
import json
import unittest
import prepare_r1_cached_admission723 as p


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=p.life.read_bound(p.CANDIDATE/'status.json',p.CANDIDATE_SEAL)
        cls.manifest=p.life.read_bound(p.BASE/'admission-manifest.json',p.BASE_SEAL)
        cls.base=json.loads((p.BASE/'status.json').read_text());cls.before=json.loads((p.BASE/'combined-bits.json').read_text())
        cls.hist=json.loads((p.life.OUT/'akv-column-boundary-offline-admitted-721-20261006-01/combined-bits.json').read_text())
        cls.single=json.loads((p.CANDIDATE/'single-raw-bits.json').read_text())
    def test_actual_candidate(self):p.candidate_contract(self.state)
    def test_actual_base(self):p.baseline_contract(self.manifest,self.base,self.before,self.hist)
    def test_no_45_hit_forgery(self):
        state=dict(self.state,targets_hit=45)
        with self.assertRaises(ValueError):p.candidate_contract(state)
    def test_unqualified_candidate(self):
        with self.assertRaises(ValueError):p.candidate_contract(dict(self.state,status='PASS_OUTCOME_ONLY'))
    def test_already_admitted(self):
        with self.assertRaises(ValueError):p.candidate_contract(dict(self.state,coverage_admitted=True))
    def test_prefix_reorder(self):
        before=deepcopy(self.before);before['tests'][0],before['tests'][1]=before['tests'][1],before['tests'][0]
        with self.assertRaises(ValueError):p.baseline_contract(self.manifest,self.base,before,self.hist)
    def test_fake_base_pass(self):
        with self.assertRaises(ValueError):p.baseline_contract(self.manifest,dict(self.base,status='PREPARED'),self.before,self.hist)
    def test_duplicate_elf(self):
        sha='a'*64
        with self.assertRaises(ValueError):p.elf_unique(sha,{'/old/input.elf':sha})
    def test_new_elf(self):self.assertFalse(p.elf_unique('a'*64,{'/old/input.elf':'b'*64})['duplicate_elf'])
    def test_duplicate_vdb(self):
        single=deepcopy(self.single);single['tests']=[self.before['tests'][0]]
        with self.assertRaises(ValueError):p.population.combine(self.before,single)
    def test_exact_population(self):
        proposed,delta=p.population.combine(self.before,self.single)
        self.assertEqual(proposed['tests'],self.before['tests']+[str(p.c.RUN/'code.vdb')]);self.assertTrue(sum(delta['metrics'].values())>0)
    def test_missing_original_prefix(self):
        before=deepcopy(self.before);before['tests'].pop()
        with self.assertRaises(ValueError):p.population.combine(before,self.single)
    def test_target539_protected(self):
        hits=json.loads((p.CANDIDATE/'target-hits.json').read_text())
        self.assertEqual([(h['metric'],h['point']['raw_index']) for h in hits if not h['hit_single']],[('line',539)])
    def test_scalar_gate_unknown_skip(self):
        result=json.loads((p.CANDIDATE/'scalar-comparison.json').read_text());result['skipped_unobservable_register_values']=1
        pre=p.life.read_bound(p.c.runner.PRE/'preflight-manifest.json',p.c.PRE_SEAL)
        with self.assertRaises(ValueError):p.c.common.scalar_exact(result,pre['reference_counts'])
    def test_vector_gate_missing_byte(self):
        vector=json.loads((p.CANDIDATE/'vector-comparison.json').read_text());vector['instructions'][0]['compared_bytes']=127
        control=json.loads((p.CANDIDATE/'lifecycle.json').read_text())
        reference=[type('Reference',(),dict(pc=int(r['pc'],16),instruction=int(r['instruction'],16),vector_writes={0:0}))()
                   for r in vector['instructions']]
        with self.assertRaises(ValueError):p.c.vector_exact(vector,control['rejected_arch_seqs'],reference)
    def test_no_implicit_formal_authorization(self):
        with self.assertRaises(ValueError):p.admit(p.life.OUT/'unused-r1-admission-test','a'*64,None)
    def test_no_user_reported_provenance(self):
        with self.assertRaises(ValueError):p.admit(p.life.OUT/'unused-r1-admission-test','a'*64,'USER_REPORTED')


if __name__=='__main__':unittest.main()
