import copy
from unittest import TestCase,main
import admit_sv39_fault_alternating773 as a

class Gates(TestCase):
    @classmethod
    def setUpClass(cls):cls.q=a.life.read_bound(a.g.QUAL,a.g.QUAL_SHA)
    def test_actual_architecture(self):a.architecture(self.q)
    def test_failure_status(self):
        q=copy.deepcopy(self.q);q['status']='FAIL'
        with self.assertRaises(ValueError):a.architecture(q)
    def test_scalar_mismatch(self):
        q=copy.deepcopy(self.q);q['scalar']['mismatch']={'bad':True}
        with self.assertRaises(ValueError):a.architecture(q)
    def test_unknown_skip(self):
        q=copy.deepcopy(self.q);q['scalar']['skipped_unobservable_register_values']=1
        with self.assertRaises(ValueError):a.architecture(q)
    def test_extra_fault(self):
        q=copy.deepcopy(self.q);q['scalar']['aligned_vector_faults'].append(q['scalar']['aligned_vector_faults'][0])
        with self.assertRaises(ValueError):a.architecture(q)
    def test_missing_VRF(self):
        q=copy.deepcopy(self.q);q['oracle']['full_VRF_bytes']=4095
        with self.assertRaises(ValueError):a.architecture(q)

if __name__=='__main__':main()
