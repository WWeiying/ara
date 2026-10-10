import copy
import unittest
import review_system_rvfi_toggle762 as r


class ObserverPartition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(r.life.ROOT/'hardware/src/ara_system.sv').read_text()
        cls.definition=next(n for n in r.t.xml(r.frozen.DB/'shape/tgl.verilog.shape.xml')
            if n.get('name')=='ara_system' and n.get('chksum')=='3385959260')

    def test_real_fanout(self):
        self.assertFalse(r.source_contract(self.source)['hardware_feedback'])

    def test_feedback_rejected(self):
        with self.assertRaises(ValueError):r.source_contract(self.source+'\nassign functional = rvfi_instr[0].valid;')

    def test_consumer_rewire_rejected(self):
        with self.assertRaises(ValueError):r.source_contract(self.source.replace('.rvfi_instr_i(rvfi_instr', '.rvfi_instr_i(other_instr'))

    def test_real_full_complement(self):
        targets,protected=r.partition(self.definition,54884)
        self.assertEqual((len(targets),len(protected)),(788,418))
        self.assertEqual(sum(p['width'] for p in targets),22126)
        self.assertEqual(sum(p['kind']=='arrays' for p in protected),19)
        self.assertTrue(any(p['attributes']['name']=='clk_i' for p in protected))
        self.assertTrue(any(p['attributes']['name']=='rst_ni' for p in protected))

    def test_port_foreign_preexcluded_rejected(self):
        for key,value in (('portnode','1'),('excluded','1'),('file','596'),('type','0')):
            d=copy.deepcopy(self.definition)
            next(n for n in d.find('tglshape') if n.get('name')=='rvfi_probes.instr.tval').set(key,value)
            with self.assertRaises(ValueError):r.partition(d,54884)

    def test_prefix_boundary(self):
        self.assertFalse(r.selected('rvfi_instr_functional'))
        self.assertFalse(r.selected('other.rvfi_instr'))
        self.assertTrue(r.selected('rvfi_instr[0].valid'))


if __name__=='__main__':unittest.main()
