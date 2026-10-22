"""Focused regression for fresh vector payloads and explicit CSR chain."""
import hashlib
import json
import time
import unittest
import strict as c
from test_strict import fixture
from model import model
from newscope import HERE,PREP

def reference_fixture(s,fault=None):
    lookup={r['pc']:(op,i) for op,rr in enumerate(s['routines']) for i,r in enumerate(rr)}
    j=-1
    for row in fixture(s):
        pair=lookup.get(row['pc'])
        if pair:
            op,i=pair;delta=5 if op>=4 else 0
            if i==0:j+=1
            g=model()['rows'][j]
            if i in (1,5+delta,13+delta):
                row['csrs']=dict(vl=g['vl'] if i==5+delta else 512,vtype=11,vstart=0)
                if fault=='vstart' and j==1 and i==5+delta:row['csrs']['vstart']=1
            if i in (2,3):
                base,values=(8,g['a']) if i==2 else (16,g['b'])
                row['vectors']={base+n:sum(values[n*64+k]<<(16*k) for k in range(64)) for n in range(8)}
                if fault=='stale_load' and j==1 and i==2:del row['vectors'][8]
            if i==4:row['vectors']={0:int.from_bytes(bytes(g['mask']),'little')}
            if op>=4 and i==9:row['fp']={0:g['b'][0]|0xffffffffffff0000}
            if i==7+delta:row['vectors']={8:sum(min(v)<<k for k,v in enumerate(g['allowed']))}
            if i==14+delta:
                row['accesses']=[(s['symbols']['output']+1+k,sum(min(g['allowed'][8*k+b])<<b for b in range(8))) for k in range(64)]
        yield row

class Freshness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s=c.specification(PREP/'run01/soc.elf')
    def test_all682_full_vector_reference_witness(self):
        r=c.audit(reference_fixture(self.s),self.s,True)
        self.assertEqual((r['target_calls'],r['helper_instructions'],len(r['retired_offloads'])),(682,12592,6141))
    def test_missing_fresh_payload_even_same_values(self):
        with self.assertRaisesRegex(ValueError,'Fresh per-call'):c.audit(reference_fixture(self.s,'stale_load'),self.s,True)
    def test_observed_nonzero_vstart(self):
        with self.assertRaisesRegex(ValueError,'Actual target CSR'):c.audit(reference_fixture(self.s,'vstart'),self.s,True)

if __name__=='__main__':
    start=time.monotonic();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Freshness))
    pins={str(HERE/n):hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ('newscope.py','model.py','elf.py','strict.py','test_strict.py','test_strict02.py','host_strict01.json')}
    with (HERE/'host_strict02.json').open('x') as f:json.dump(dict(status='PASS_HOST_ONLY' if r.wasSuccessful() else 'FAIL_HOST',tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),elapsed_s=time.monotonic()-start,pins=pins,prior_host='host_strict01.json'),f,indent=2)
    raise SystemExit(not r.wasSuccessful())
