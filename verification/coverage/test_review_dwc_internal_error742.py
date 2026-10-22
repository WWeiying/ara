import unittest
import re
import review_dwc_internal_error742 as r


class DWC(unittest.TestCase):
    def source(self):return [(r.ROOT/r.SOURCES[i]).read_text() for i in (4,6,8)]
    def test_actual_source(self):self.assertEqual(r.source_contract(*self.source())['error_assignment_paths'],3)
    def test_AR_WRAP_mutation(self):
        s,u,d=self.source();s,count=re.subn(r'(axi_req_o\.ar\.burst\s*=\s*)axi_pkg::BURST_INCR',r'\1axi_pkg::BURST_WRAP',s)
        self.assertEqual(count,1)
        with self.assertRaises(ValueError):r.source_contract(s,u,d)
    def test_AW_WRAP_mutation(self):
        s,u,d=self.source();s=s.replace('axi_req_o.aw.burst = axi_pkg::BURST_INCR','axi_req_o.aw.burst = axi_pkg::BURST_WRAP')
        with self.assertRaises(ValueError):r.source_contract(s,u,d)
    def test_unconditional_error(self):
        s,u,d=self.source();u+="\nr_req_d.ar_throw_error = 1'b1;\n"
        with self.assertRaises(ValueError):r.source_contract(s,u,d)
    def test_injected_burst_source(self):
        s,u,d=self.source();u=u.replace('r_req_d.ar.burst     = w_req_q.aw.burst','r_req_d.ar.burst     = axi_pkg::BURST_WRAP')
        with self.assertRaises(ValueError):r.source_contract(s,u,d)
    def test_bad_demux_gate(self):
        s,u,d=self.source();d=d.replace('slv_ar_select_i == i','1 == i')
        with self.assertRaises(ValueError):r.source_contract(s,u,d)
    def test_all_lengths_ATOP(self):self.assertEqual(r.induction()['combinations'],98304)


if __name__=='__main__':unittest.main()
