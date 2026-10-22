import copy
import unittest
import admit_qbs_affine_aux747 as a


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qual = a.life.read_bound(a.QUAL/'qualification.json', a.QUAL_SHA)

    def test_actual_exact_native_scope(self):
        a.qualification_contract(self.qual)

    def test_full_isa_claim_rejected(self):
        q = copy.deepcopy(self.qual); q['full_scalar_ISA_verified'] = True
        with self.assertRaises(ValueError): a.qualification_contract(q)

    def test_missing_checks_rejected(self):
        q = copy.deepcopy(self.qual); q['checks'] = 40
        with self.assertRaises(ValueError): a.qualification_contract(q)

    def test_wrong_baseline_rejected(self):
        q = copy.deepcopy(self.qual); q['baseline'] = 745
        with self.assertRaises(ValueError): a.qualification_contract(q)

    def test_bool_count_rejected(self):
        q = copy.deepcopy(self.qual); q['native_active_bytes'] = True
        with self.assertRaises(ValueError): a.qualification_contract(q)

    def test_zero_gain_rejected(self):
        q = copy.deepcopy(self.qual); q['raw_delta'] = dict(line=0, cond=0, branch=0, fsm=0)
        with self.assertRaises(ValueError): a.qualification_contract(q)

    def test_missing_reset_proof_rejected(self):
        q = copy.deepcopy(self.qual); q['reset_stage_and_slot_reuse_wave_verified'] = False
        with self.assertRaises(ValueError): a.qualification_contract(q)


if __name__ == '__main__': unittest.main()
