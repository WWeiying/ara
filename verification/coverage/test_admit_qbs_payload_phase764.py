import copy
import json
from pathlib import Path
import unittest

import admit_qbs_payload_phase764 as a


class TestAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((a.BASE/'combined-bits.json').read_bytes())
        cls.qual=a.life.read_bound(a.QUAL/'qualification.json',a.QUAL_SHA)
        cls.audit=json.loads((a.QUAL/'runtime-audit.json').read_bytes())

    def sample(self):
        single=copy.deepcopy(self.before);single['tests']=[str(a.RUN/'code.vdb')]
        return single

    def test_actual_sealed_native_contract(self):a.contract(self.qual,self.audit)

    def test_wrong_qualification_scope(self):
        for key,value in [('full_scalar_isa_verified',True),('native_destination_bytes',511),
                          ('source_guard_bytes',0),('coverage_admitted',True)]:
            qual=dict(self.qual);qual[key]=value
            with self.assertRaises(ValueError):a.contract(qual,self.audit)

    def test_bool_not_count(self):
        qual=dict(self.qual);qual['csr_words']=True
        with self.assertRaises(ValueError):a.contract(qual,self.audit)

    def test_nonzero_exception(self):
        audit=copy.deepcopy(self.audit);audit['contract']['exceptions']=1
        with self.assertRaises(ValueError):a.contract(self.qual,audit)

    def test_missing_native_owner_or_backend_shape(self):
        audit=copy.deepcopy(self.audit);audit['bindings'].pop()
        with self.assertRaises(ValueError):a.contract(self.qual,audit)
        audit=copy.deepcopy(self.audit);audit['bindings'][0]['backend_vl']=160
        with self.assertRaises(ValueError):a.contract(self.qual,audit)

    def test_exact_actual763_prefix_and_6162_OR(self):
        combined,delta=a.merge(self.before,self.sample())
        self.assertEqual(combined['tests'],self.before['tests']+[str(a.RUN/'code.vdb')])
        self.assertEqual(len(combined['tests']),764)
        self.assertEqual(delta['metrics'],dict(line=0,cond=0,branch=0,fsm=0))

    def test_duplicate_baseline_rejected(self):
        before=copy.deepcopy(self.before);before['tests'][-1]=before['tests'][0]
        with self.assertRaises(ValueError):a.merge(before,self.sample())

    def test_wrong_candidate_rejected(self):
        single=self.sample();single['tests']=['/not/the/qualified/vdb']
        with self.assertRaises(ValueError):a.merge(self.before,single)

    def test_missing_instance_rejected(self):
        single=self.sample();single['metrics']['fsm'].pop(next(iter(single['metrics']['fsm'])))
        with self.assertRaises(ValueError):a.merge(self.before,single)

    def test_shape_checksum_rejected(self):
        single=self.sample();next(iter(single['metrics']['fsm'].values()))['checksum']='0'
        with self.assertRaises(ValueError):a.merge(self.before,single)

    def test_zero_gain_rejected(self):
        with self.assertRaises(ValueError):a.positive(dict(metrics=dict(line=0,cond=0,branch=0,fsm=0)),0)
        a.positive(dict(metrics=dict(line=0,cond=0,branch=0,fsm=0)),288)

    def test_actual_compiled_mapping_every_predicted_coordinate(self):
        prediction=json.loads((a.q.runner.PRE/'target-prediction.json').read_bytes())
        gains=sorted(c for t in prediction['targets'] for c in t['missing_serialized_coordinates'])
        root=a.toggle.xml(Path(str(a.life.IMAGE)+'.vdb')/'snps/coverage/db/shape/tgl.verilog.shape.xml')
        definition=next(d for d in root.iter('tgldef') if d.get('chksum')=='3657545390')
        fields=a.field_map(definition,66340,gains)
        self.assertEqual(sum(len(f['raw_coordinates']) for f in fields),288)
        self.assertTrue(all(f['declaration_line']=='381' for f in fields))
        actual={(f['signal'],slot['bit'],slot['coordinate']) for f in fields for slot in f['bit_pair_slots']}
        expected={(t['signal'],t['bit'],c) for t in prediction['targets'] for c in t['missing_serialized_coordinates']}
        self.assertEqual(actual,expected)
        with self.assertRaises(ValueError):a.field_map(definition,66339,gains)


if __name__=='__main__':unittest.main()
