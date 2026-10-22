"""All-producer write singleton invariant and legal AMO injection counterexamples."""
import unittest
import review_scalar_dwc_write_fsm as m


class ProducerProof(unittest.TestCase):
    def source(self):
        return [(m.life.ROOT/p).read_text() for p in (
            'hardware/deps/cva6/core/cache_subsystem/wt_axi_adapter.sv',
            'hardware/deps/cva6/core/axi_shim.sv','hardware/deps/axi/src/axi_dw_upsizer.sv')]

    def test_actual_frozen_contract(self):
        c=m.contract(*self.source())
        self.assertEqual(c['aw_len'],0)
        self.assertTrue(c['aw_atop_not_constant_zero'])

    def test_nonzero_write_length(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a.replace("axi_wr_blen  = '0","axi_wr_blen  = '1"),s,u)

    def test_later_assignment(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a+"\naxi_wr_blen = '0;",s,u)

    def test_wrong_len_port(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a.replace('.wr_blen_i  (axi_wr_blen)','.wr_blen_i  (axi_rd_blen)'),s,u)

    def test_shim_len_override(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a,s.replace('axi_req_o.aw.len = wr_blen_i','axi_req_o.aw.len = rd_blen_i'),u)

    def test_gate_removed(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a,s,u.replace("if (slv_req_i.aw.len != '0)",'if (1)'))

    def test_extra_state_entry(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a,s,u+'\nw_state_d = W_INCR_UPSIZE;')

    def test_atop_false_premise_rejected(self):
        a,s,u=self.source()
        with self.assertRaises(ValueError):m.contract(a,s.replace('axi_req_o.aw.atop = wr_atop_i',"axi_req_o.aw.atop = '0"),u)

    def test_legal_positive_counterexamples(self):
        self.assertEqual(m.entry(0),'W_PASSTHROUGH')
        self.assertEqual(m.entry(1),'W_INCR_UPSIZE')
        self.assertEqual(m.entry(1,False),'W_PASSTHROUGH')
        self.assertEqual(m.entry(1,True,'FIXED'),'W_PASSTHROUGH')
        self.assertTrue(0x20&(1<<5));self.assertTrue(0x30&(1<<5))

    def test_actual_shape_no_read_candidates(self):
        root=m.prior.t.xml(m.DB/'shape/fsm.verilog.shape.xml')
        ds=[d for d in root.iter('fsmdef') if d.get('chksum')=='3866098985' and
            any(n.get('name')==m.prior.DWC for n in d.findall('fsminst'))]
        row={'width':31,'bits':'0x55db1db1'}
        result=m.points(ds[0],row)
        self.assertEqual([p['raw_index'] for p in result if p['candidate']],[1,3,5])
        self.assertTrue(all(not p['candidate'] for p in result if p['machine']!='w_state_d'))
        with self.assertRaises(ValueError):m.points(ds[0],dict(row,bits=hex(int(row['bits'],16)|(1<<(31-1-1)))))


if __name__=='__main__':unittest.main()
