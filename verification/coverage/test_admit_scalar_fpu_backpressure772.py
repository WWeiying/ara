import copy
import unittest
from unittest.mock import patch
import admit_scalar_fpu_backpressure772 as a

class Tests(unittest.TestCase):
    def test_real_functional_contract(self):a.functional_gate(a.life.read_bound(a.gain.DIAG,a.gain.DIAG_SHA))
    def test_gold_and_holding_mutations(self):
        original=a.life.read_bound(a.gain.DIAG,a.gain.DIAG_SHA)
        for key,index in (('results',0),('csr',2),('guards',0)):
            q=copy.deepcopy(original);q[key][index]^=1
            with self.subTest(key=key),self.assertRaises(ValueError):a.functional_gate(q)
        q=copy.deepcopy(original);q['backpressure']['captured_released']=11
        with self.assertRaises(ValueError):a.functional_gate(q)
    def fixture(self):
        before=dict(tests=['old%d'%i for i in range(771)],design={'d':'1'},input_hashes={},
            metrics={'cond':{str(i):dict(width=1,checksum='1',bits='0x0') for i in range(6162)}})
        single=dict(before,tests=[str(a.p.RUN/'code.vdb')])
        return before,single,a.p.bitmap.combine(before,single)
    def test_full_prefix_OR(self):
        before,single,after=self.fixture();a.union_gate(before,single,after)
        after['tests'][0]='changed'
        with self.assertRaises(ValueError):a.union_gate(before,single,after)
    def test_duplicate_wrong_shape_dropped_instance(self):
        before,single,after=self.fixture()
        single['tests']=[before['tests'][0]]
        with self.assertRaises(ValueError):a.union_gate(before,single,after)
        before,single,after=self.fixture();del after['metrics']['cond']['0']
        with self.assertRaises(ValueError):a.union_gate(before,single,after)
        before,single,after=self.fixture();single['metrics']=copy.deepcopy(single['metrics'])
        single['metrics']['cond']['0']['checksum']='2'
        with self.assertRaises(ValueError):a.union_gate(before,single,after)
    def test_zero_gain_rejected(self):
        with self.assertRaises(ValueError):a.gain.positive(dict(line=0,cond=0,branch=0,fsm=0),0)

if __name__=='__main__':unittest.main()
