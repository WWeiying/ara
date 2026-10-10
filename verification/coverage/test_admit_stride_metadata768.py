import copy
import json
import unittest
import admit_stride_metadata768 as p


class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=json.loads((p.QUAL/'qualification.json').read_bytes())
        cls.scalar=json.loads((p.QUAL/'scalar-comparison.json').read_bytes())
        cls.vector=json.loads((p.QUAL/'vector-comparison.json').read_bytes())
    def reject(self,q=None,scalar=None,vector=None):
        with self.assertRaises(ValueError):p.contract(q or self.q,scalar or self.scalar,vector or self.vector)
    def test_actual(self):p.contract(self.q,self.scalar,self.vector)
    def test_failed(self):
        q=copy.deepcopy(self.q);q['status']='FAIL';self.reject(q=q)
    def test_missing_checks(self):
        q=copy.deepcopy(self.q);q['signature']['checks']=604;self.reject(q=q)
    def test_exception(self):
        q=copy.deepcopy(self.q);q['lifecycle']['exceptions']=1;self.reject(q=q)
    def test_unknown(self):
        v=copy.deepcopy(self.vector);v['skipped_unknown_bytes']=1;self.reject(vector=v)
    def test_wrong_baseline(self):
        q=copy.deepcopy(self.q);q['baseline']=766;self.reject(q=q)
    def test_no_gain(self):
        q=copy.deepcopy(self.q);q['raw_gain']['target_new_serialized_directions']=0;self.reject(q=q)
    def test_scalar_mismatch(self):
        s=copy.deepcopy(self.scalar);s['mismatch']={'bad':True};self.reject(scalar=s)
    def test_duplicate_elf(self):
        ledger=[str(p.case.life.IMAGE)+'.vdb',str(p.RUN/'code.vdb')]
        newhash=p.life.digest(p.OUT/'stride-metadata-full64-preflight767-agent-20261007-02/input.elf')
        with self.assertRaises(ValueError):p.dedup(ledger,newhash)


if __name__=='__main__':unittest.main()
