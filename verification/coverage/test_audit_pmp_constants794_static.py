import unittest
import audit_pmp_constants794_static as a


class PMPProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts={}
        for rel in a.FILES:
            p=a.ROOT/rel;cls.texts[p.name]=p.read_text()

    def test_actual_pmp_zero(self):
        p=a.proof(self.texts)
        self.assertEqual(p['actual_NrPMPEntries'],0)
        self.assertEqual(p['compiled_dummy_port_indices'],[0])

    def test_nonzero_entries_rejected(self):
        t=dict(self.texts);t['ara_soc.sv']=t['ara_soc.sv'].replace('cfg.NrPMPEntries          = 0;','cfg.NrPMPEntries          = 1;')
        with self.assertRaises(Exception):a.proof(t)

    def test_unimplemented_next_mutation_rejected(self):
        t=dict(self.texts);t['csr_regfile.sv']=t['csr_regfile.sv'].replace("pmpcfg_next[i]  = '0;",'pmpcfg_next[i]  = pmpcfg_d[i];')
        with self.assertRaises(Exception):a.proof(t)

    def test_reflection_mutation_rejected(self):
        t=dict(self.texts);t['csr_regfile.sv']=t['csr_regfile.sv'].replace('rvfi_csr_o.pmpcfg_q = pmpcfg_q','rvfi_csr_o.pmpcfg_q = pmpcfg_d')
        with self.assertRaises(Exception):a.proof(t)

    def test_dynamic_reserved_is_not_constant(self):
        self.assertFalse(a.in_family('pmpcfg_d[0].reserved','pmpcfg_q'))
        self.assertEqual(a.prior.pending_model(0,[255]*64),[0]*64)
        self.assertNotEqual(a.prior.pending_model(1,[255]*64),[0]*64)

    def test_probe_pmp_override_rejected(self):
        t=dict(self.texts);t['cva6_rvfi_probes.sv']=t['cva6_rvfi_probes.sv'].replace('csr = csr_i;','csr = csr_i; csr.pmpcfg_q = \'1;')
        with self.assertRaises(Exception):a.proof(t)


if __name__=='__main__':unittest.main()
