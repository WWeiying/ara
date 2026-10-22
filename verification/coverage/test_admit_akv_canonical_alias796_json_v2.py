import copy
import json
import unittest
import admit_akv_canonical_alias796_json_v2 as v
from test_admit_akv_canonical_alias796 import Admission


class Serialization(unittest.TestCase):
    def fixture(self):
        q=v.life.read_bound(v.old.QUAL/'qualification.json',v.old.Q_SHA)
        p=v.old.QUAL/'lifecycle.json';saved=v.life.read_bound(p,q['output_pins'][str(p)])
        actual=copy.deepcopy(saved)
        for name in ('starts','allocations','done'):actual[name]={int(k):r for k,r in actual[name].items()}
        return actual,saved

    def test_actual_sealed_lifecycle_keys(self):
        a,s=self.fixture();self.assertTrue(v.lifecycle_equal(a,s))

    def test_wrong_owner_or_field_not_ignored(self):
        a,s=self.fixture()
        for name in ('starts','allocations','done'):
            bad=copy.deepcopy(s);key=next(iter(bad[name]));bad[name][key]['insn']^=1
            self.assertFalse(v.lifecycle_equal(a,bad))
        bad=copy.deepcopy(s);bad['commands'][0]['seq']+=1;self.assertFalse(v.lifecycle_equal(a,bad))

    def test_noncanonical_sequence_and_boolean_rejected(self):
        a,s=self.fixture();bad=copy.deepcopy(s);k=next(iter(bad['starts']));bad['starts']['0'+k]=bad['starts'].pop(k)
        with self.assertRaises(ValueError):v.lifecycle_equal(a,bad)
        bad=copy.deepcopy(s);k=next(iter(bad['starts']));bad['starts'][k]['trap']=False
        self.assertFalse(v.lifecycle_equal(a,bad))

    def test_actual_native_capture_tuple_serialization(self):
        q=v.life.read_bound(v.old.QUAL/'qualification.json',v.old.Q_SHA)
        p=v.old.QUAL/'native-capture.json';saved=v.life.read_bound(p,q['output_pins'][str(p)])
        def tuples(node):
            if isinstance(node,dict):return {k:([tuple(r) for r in value] if k=='ranges' else tuples(value)) for k,value in node.items()}
            if isinstance(node,list):return [tuples(r) for r in node]
            return node
        actual=tuples(saved);self.assertTrue(v.native_equal(actual,saved))
        bad=copy.deepcopy(saved);bad['extra_field']=0;self.assertFalse(v.native_equal(actual,bad))
        def mutate(node):
            if isinstance(node,dict):
                for key,value in node.items():
                    if key=='ranges' and value:
                        value[0][0]+=1;return True
                    if mutate(value):return True
            if isinstance(node,list):
                for row in node:
                    if mutate(row):return True
            return False
        bad=copy.deepcopy(saved);self.assertTrue(mutate(bad));self.assertFalse(v.native_equal(actual,bad))
        self.assertFalse(v.native_equal({'flag':False},{'flag':0}))


if __name__=='__main__':unittest.main()
