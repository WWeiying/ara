"""Frozen actual source/point fixtures; reject wider waiver or configuration drift."""
from copy import deepcopy
import unittest
import prepare_memory_emul_r2_lower_candidate as p


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=p.life.read_bound(p.PRE/'preflight-manifest.json',p.PRE_SEAL)
        cls.text=p.SOURCE.read_text()
    def test_exact92_encoded_combinations(self):
        proof=p.encoded_proof();self.assertEqual(len(proof['rows']),92)
        self.assertTrue(all(not r['lower_arm'] for r in proof['rows']))
    def test_includes_reset_and_vill(self):
        self.assertEqual(sum(r['vill'] for r in p.encoded_proof()['rows']),4)
    def test_signed3_difference_no_wrap(self):
        self.assertTrue(all(-3<=r['delta_signed3']<=3 for r in p.encoded_proof()['rows']))
    def test_ELEN_drift_rejected(self):
        for value in (32,128):
            with self.assertRaises(ValueError):p.encoded_proof(value)
    def test_actual_source_write_sites(self):
        self.assertEqual(len(p.source_contract(self.text)['csr_vtype_write_sites']),5)
    def test_unreviewed_CSR_write_rejected(self):
        with self.assertRaises(ValueError):p.source_contract(self.text+'\ncsr_vtype_d.vlmul = LMUL_1_8;\n')
    def test_normalization_change_rejected(self):
        with self.assertRaises(ValueError):p.source_contract(self.text.replace("csr_vtype_d = '{vill: 1'b1, vsew: EW8, vlmul: LMUL_1, default: '0};",
                                                                         "csr_vtype_d = '{vill: 1'b1, vsew: EW64, vlmul: LMUL_1_8, default: '0};"))
    def test_actual_four_identities(self):
        targets=p.candidate_targets(self.pre['targets'])
        self.assertEqual({(t['metric'],t['point']['raw_index']) for t in targets},p.ALLOWED)
    def test_missing_candidate_rejected(self):
        targets=p.candidate_targets(self.pre['targets'])
        with self.assertRaises(ValueError):p.candidate_targets(targets[:-1])
    def test_duplicate_candidate_rejected(self):
        targets=p.candidate_targets(self.pre['targets'])
        with self.assertRaises(ValueError):p.candidate_targets([*targets,targets[0]])
    def test_hit_candidate_rejected(self):
        targets=deepcopy(self.pre['targets']);next(t for t in targets if t['point']['raw_index']==1228)['hit721']=True
        with self.assertRaises(ValueError):p.candidate_targets(targets)
    def test_upper_is_not_candidate(self):
        self.assertFalse(any(t['expected_case']==2 for t in p.candidate_targets(self.pre['targets'])))


if __name__=='__main__':unittest.main()
