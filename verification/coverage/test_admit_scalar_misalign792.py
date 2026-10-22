import copy
import unittest
from unittest.mock import patch
import admit_scalar_misalign792 as m


class Joint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=m.life.read_bound(m.QUAL/'qualification.json',m.CORE_SHA)
        cls.cl=m.life.read_bound(m.QUAL/'soc-width-closure.json',m.CLOSURE_SHA)
    def test_actual_joint_source_closure(self):m.joint_gate(self.q,self.cl)
    def test_missing_closure_rejected(self):
        with self.assertRaises((ValueError,KeyError)):m.joint_gate(self.q,{})
    def test_wrong_core_pointer_rejected(self):
        cl=copy.deepcopy(self.cl);cl['core_sha256']='0'*64
        with self.assertRaises(ValueError):m.joint_gate(self.q,cl)
    def test_only_one_fault_rejected(self):
        q=dict(self.q,native_faults=1)
        with self.assertRaises(ValueError):m.joint_gate(q,self.cl)
    def test_bool_retirement_rejected(self):
        q=dict(self.q,scalar_retirements=True)
        with self.assertRaises(ValueError):m.joint_gate(q,self.cl)
    def test_adapter_test_pin_omission_rejected(self):
        cl=copy.deepcopy(self.cl);p=str(m.Path(m.a.__file__).with_name('test_scalar_misalign789_soc_width_adapter.py'))
        cl['input_pins'].pop(p)
        with self.assertRaises(ValueError):m.joint_gate(self.q,cl)
    def test_fake_proof_width_rejected(self):
        cl=copy.deepcopy(self.cl);cl['source_proof']['layouts']['dcache_req_i_t']['width']=199
        with self.assertRaises(ValueError):m.joint_gate(self.q,cl)


class Union(unittest.TestCase):
    def fixture(self):
        metrics={k:{'s%d'%i:dict(width=2,checksum='1',bits='0x0') for i in range(n)} for k,n in m.COUNTS.items()}
        before=dict(design={'shape':'sealed'},tests=['v%d'%i for i in range(791)],metrics=metrics,input_hashes={})
        single=copy.deepcopy(before);single['tests']=['new'];single['metrics']['cond']['s0']['bits']='0x1'
        return before,single
    def test_exact6162_union_prefix(self):
        b,s=self.fixture();out=m.full_union(b,s)
        self.assertEqual(len(out['tests']),792);self.assertEqual(out['metrics']['cond']['s0']['bits'],'0x1')
    def test_duplicate_vdb_rejected(self):
        b,s=self.fixture();s['tests']=['v0']
        with self.assertRaises(ValueError):m.full_union(b,s)
    def test_missing_scope_rejected(self):
        b,s=self.fixture();s['metrics']['cond'].pop('s0')
        with self.assertRaises(ValueError):m.full_union(b,s)
    def test_checksum_mismatch_rejected(self):
        b,s=self.fixture();s['metrics']['cond']['s0']['checksum']='2'
        with self.assertRaises(ValueError):m.full_union(b,s)
    def test_out_of_range_bit_rejected(self):
        b,s=self.fixture();s['metrics']['cond']['s0']['bits']='0x8'
        with self.assertRaises(ValueError):m.full_union(b,s)


if __name__=='__main__':unittest.main()
