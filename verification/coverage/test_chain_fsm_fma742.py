import json
import unittest
import chain_fsm_fma742 as m


class NativeUnion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fc=json.loads((m.FMA/'config.json').read_bytes())
        cls.text=(m.CAPTURE/'combined.el').read_text()+(m.base.OBS/'observers.el').read_text()+(m.FMA/'first.el').read_text()

    def test_exact_native_union(self):
        fsm,obs,fma=m.records(self.text,self.fc)
        self.assertEqual((len(fsm),len(obs),len(fma)),(124,4,108))

    def test_duplicate_fsm_rejected(self):
        with self.assertRaises(ValueError): m.records(self.text+(m.CAPTURE/'combined.el').read_text(),self.fc)

    def test_fma_annotation_rejected(self):
        with self.assertRaises(ValueError): m.records(self.text.replace(m.ANNOTATION,'foreign'),self.fc)

    def test_fma_signature_rejected(self):
        with self.assertRaises(ValueError): m.records(self.text.replace('logic product[105:0]','logic product[104:0]'),self.fc)

    def test_sequential_merge_conflict_rejected(self):
        a={'/sealed/a':'a'*64}
        b={'/sealed/b':'b'*64}
        self.assertEqual(m.merge_inventories(a,b,a),dict(a,**b))
        with self.assertRaises(ValueError): m.merge_inventories(a,b,{'/sealed/a':'c'*64})


if __name__=='__main__': unittest.main()
