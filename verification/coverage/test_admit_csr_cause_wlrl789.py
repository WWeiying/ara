import copy
import json
import unittest
from unittest.mock import patch
import admit_csr_cause_wlrl789 as m

class AdmissionTests(unittest.TestCase):
    def population(self):
        row=dict(width=2,checksum='123',bits='0')
        before=dict(design={},tests=['old%d'%i for i in range(788)],input_hashes={'/fixture':'a'*64},metrics={k:{'scope':dict(row)} for k in m.COUNTS})
        single=copy.deepcopy(before);single['tests']=[str(m.RUN/'code.vdb')]
        for scopes in single['metrics'].values():scopes['scope']['bits']='1'
        return before,single
    def union(self,a,b):
        with patch.object(m,'COUNTS',{k:1 for k in m.COUNTS}):return m.full_union(a,b)
    def test_prefix_and_or(self):
        a,b=self.population();r=self.union(a,b);self.assertEqual(r['tests'],a['tests']+b['tests'])
        self.assertTrue(all(int(v['scope']['bits'],16)==1 for v in r['metrics'].values()))
    def test_duplicate_vdb(self):
        a,b=self.population();a['tests'][0]=b['tests'][0]
        with self.assertRaises(ValueError):self.union(a,b)
    def test_missing_metric(self):
        a,b=self.population();del b['metrics']['fsm']
        with self.assertRaises(ValueError):self.union(a,b)
    def test_wrong_shape(self):
        a,b=self.population();b['metrics']['line']['scope']['checksum']='9'
        with self.assertRaises(ValueError):self.union(a,b)
    def test_wrong_width(self):
        a,b=self.population();b['metrics']['line']['scope']['width']=3
        with self.assertRaises(ValueError):self.union(a,b)
    def test_bool_width(self):
        a,b=self.population()
        for v in (a,b):v['metrics']['line']['scope']['width']=True
        with self.assertRaises(ValueError):self.union(a,b)
    def test_out_of_bounds_bits(self):
        a,b=self.population();b['metrics']['line']['scope']['bits']='8'
        with self.assertRaises(ValueError):self.union(a,b)
    def test_conflicting_pins(self):
        a,b=self.population();a['input_hashes']={'/path':'a'*64};b['input_hashes']={'/path':'b'*64}
        with self.assertRaises(ValueError):self.union(a,b)
    def targets(self):
        t=json.loads((m.run.PRE/'target-before.json').read_text());scopes={f['scope'] for f in t['fields']}
        p=m.RUN/'code.vdb/snps/coverage/db/testdata'/m.run.NAME/'tgl.verilog.data.xml'
        sample,_=m.run.oracle.prior.toggle.rows(p,scopes);return t,sample
    def test_actual928_typed_gain(self):
        t,s=self.targets();self.assertEqual(sum(len(f['gained']) for f in m.typed_gain(t,s)),928)
    def test_zero_toggle_gain(self):
        t,s=self.targets()
        for r in s.values():r['bits']='0'
        with self.assertRaises(ValueError):m.typed_gain(t,s)
    def test_duplicate_target(self):
        t,s=self.targets();t['fields'][-1]=copy.deepcopy(t['fields'][0])
        with self.assertRaises(ValueError):m.typed_gain(t,s)
    def test_wrong_population(self):
        t,s=self.targets();t['baseline']=787
        with self.assertRaises(ValueError):m.typed_gain(t,s)
    def test_wrong_coordinate(self):
        t,s=self.targets();t['fields'][0]['missing_coordinates'][0]=-1
        with self.assertRaises(ValueError):m.typed_gain(t,s)
if __name__=='__main__':unittest.main()
