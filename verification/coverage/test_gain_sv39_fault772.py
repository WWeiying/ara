from unittest import TestCase,main
import copy
import gain_sv39_fault_alternating772 as q

class DesignTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=q.life.read_bound(q.BASE/'admission-manifest.json',q.BASE_SHA)
        cls.before=q.life.read_bound(q.BASE/'combined-bits.json',cls.base['output_pins'][str(q.BASE/'combined-bits.json')])
        cls.design=q.Path((q.BASE/'combined-inputs.txt').read_text().splitlines()[0])
    def test_real_compile(self):self.assertEqual(len(q.design_contract(self.before,self.design,self.base)),5)
    def test_test_vdb_is_not_design(self):
        with self.assertRaises((ValueError,FileNotFoundError)):q.design_contract(self.before,q.Path(self.before['tests'][0]),self.base)
    def test_wrong_design_hash(self):
        b=copy.deepcopy(self.before);b['design']['design/verilog.design.xml']='a'*64
        with self.assertRaises(ValueError):q.design_contract(b,self.design,self.base)
    def test_wrong_shape_hash(self):
        b=copy.deepcopy(self.before);b['design']['shape/fsm.verilog.shape.xml']='a'*64
        with self.assertRaises(ValueError):q.design_contract(b,self.design,self.base)
    def test_missing_manifest_pin(self):
        m=copy.deepcopy(self.base);m['input_pins'].pop(str(self.design/'snps/coverage/db/design/verilog.design.xml'))
        with self.assertRaises(ValueError):q.design_contract(self.before,self.design,m)

if __name__=='__main__':main()
