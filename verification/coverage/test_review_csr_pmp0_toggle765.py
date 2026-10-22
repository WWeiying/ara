"""PMP0 proof mutation checks only; no EDA, simulator or native approval."""
import unittest
import review_csr_pmp0_toggle765 as m


class ProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.sources=[(m.ROOT/p).read_text() for p in m.REL[:3]]

    def test_frozen_config_constant_contract(self):
        self.assertTrue(m.source_proof(*self.sources)['d_protected'])

    def test_nonzero_or_additional_override(self):
        for text in (self.sources[0].replace('cfg.NrPMPEntries          = 0;','cfg.NrPMPEntries = 8;'),
                     self.sources[0]+'\ncfg.NrPMPEntries=1;'):
            self.assertNotEqual(text,self.sources[0])
            with self.assertRaises(ValueError):m.source_proof(text,*self.sources[1:])

    def test_lost_config_propagation(self):
        text=self.sources[1].replace('cfg.NrPMPEntries = CVA6Cfg.NrPMPEntries;','cfg.NrPMPEntries = 8;')
        self.assertNotEqual(text,self.sources[1])
        with self.assertRaises(ValueError):m.source_proof(self.sources[0],text,self.sources[2])

    def test_reset_nonzero(self):
        text=self.sources[2].replace("pmpaddr_q[i] <= '0;","pmpaddr_q[i] <= '1;")
        self.assertNotEqual(text,self.sources[2])
        with self.assertRaises(ValueError):m.source_proof(*self.sources[:2],text)

    def test_next_or_output_from_dynamic_d(self):
        for old,new in [("pmpaddr_next[i] = '0;","pmpaddr_next[i] = pmpaddr_d[i];"),
                        ('assign pmpaddr_o = pmpaddr_q','assign pmpaddr_o = pmpaddr_d')]:
            text=self.sources[2].replace(old,new);self.assertNotEqual(text,self.sources[2])
            with self.assertRaises(ValueError):m.source_proof(*self.sources[:2],text)

    def test_added_q_writer(self):
        for extra in ("pmpcfg_q <= '1;", "pmpcfg_q[0].locked <= 1'b1;"):
            with self.assertRaises(ValueError):m.source_proof(*self.sources[:2],self.sources[2]+'\n'+extra)

    def test_known_byte_induction_and_configuration_boundary(self):
        for value in range(256):self.assertEqual(m.pending_model(0,[value]*64),[0]*64)
        self.assertNotEqual(m.pending_model(1,[255]*64),[0]*64)


if __name__=='__main__':unittest.main()
