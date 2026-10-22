import copy
import json
import unittest
import admit_qbs_payload_residual4_767 as m


class Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qual=json.loads((m.QUAL/'qualification.json').read_bytes())
        cls.audit=json.loads((m.QUAL/'runtime-audit.json').read_bytes())

    def test_actual_qualification(self):m.contract(self.qual,self.audit)

    def test_incomplete_changed_or_oversold_qualification(self):
        for key in ('full_vrf_bytes','native_destination_bytes','csr_values','commands','source_readback_bytes','baseline','total_new_raw_directions','measured_predicted_directions'):
            q=copy.deepcopy(self.qual);q[key]-=1
            with self.assertRaises(ValueError):m.contract(q,self.audit)
        q=copy.deepcopy(self.qual);q['full_scalar_isa_verified']=True
        with self.assertRaises(ValueError):m.contract(q,self.audit)

    def test_observer_source_or_missing_phase_rejected(self):
        for which in ('observer','phase','guard','trap'):
            a=copy.deepcopy(self.audit)
            if which=='observer':a['source_observer_contract']['semantics']='x0 register proof'
            elif which=='phase':a['bindings'].pop()
            elif which=='guard':a['bindings'][0]['readback_bytes']['frame0']-=1
            else:a['contract']['exceptions']=1
            with self.assertRaises(ValueError):m.contract(self.qual,a)

    def fixture(self):
        before=dict(design={'shape':'same'},tests=['case%d'%i for i in range(766)],input_hashes={},metrics={})
        single=dict(design={'shape':'same'},tests=[str(m.RUN/'code.vdb')],input_hashes={},metrics={})
        for metric in m.bitmap.METRICS:
            before['metrics'][metric]={};single['metrics'][metric]={}
            for i in range(1542 if metric in ('line','cond') else 1539):
                row=dict(width=4,checksum='42',bits='0x1')
                before['metrics'][metric]['scope%d'%i]=row
                single['metrics'][metric]['scope%d'%i]=dict(row,bits='0x2')
        return before,single

    def test_full6162_or_prefix(self):
        b,s=self.fixture();c,d=m.merge(b,s)
        self.assertEqual(c['tests'],b['tests']+s['tests'])
        self.assertEqual(c['metrics']['line']['scope0']['bits'],'0x3')

    def test_population_shape_overflow_duplicate_rejected(self):
        for which in ('duplicate','width','checksum','missing','overflow','population','design'):
            b,s=self.fixture()
            if which=='duplicate':b['tests'][0]=s['tests'][0]
            elif which=='width':s['metrics']['cond']['scope0']['width']=5
            elif which=='checksum':s['metrics']['cond']['scope0']['checksum']='43'
            elif which=='missing':s['metrics']['cond'].pop('scope0')
            elif which=='overflow':s['metrics']['cond']['scope0']['bits']='0x100'
            elif which=='population':b['tests'].pop()
            else:s['design']['shape']='other'
            with self.assertRaises(ValueError):m.merge(b,s)

    def test_zero_gain_rejected(self):
        with self.assertRaises(ValueError):m.prior.positive(dict(metrics=dict(line=0,cond=0,branch=0,fsm=0)),0)


if __name__=='__main__':unittest.main()
