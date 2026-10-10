import unittest
import audit_pmp_constants794_static_v2 as a


class WriterClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts={}
        for rel in a.old.FILES:
            p=a.old.ROOT/rel;cls.texts[p.name]=p.read_text()

    def test_actual_complete_writers(self):
        self.assertEqual(a.writer_guard(self.texts)['parent_alias_reference_counts'],dict(pmpcfg=4,pmpaddr=4,rvfi_csr=3))

    def reject_extra(self,file,code):
        texts=dict(self.texts);texts[file]+='\n'+code
        with self.assertRaises(Exception):a.writer_guard(texts)

    def test_additional_reflection_whole_writer(self):
        self.reject_extra('csr_regfile.sv',"always_comb rvfi_csr_o = '1;")

    def test_additional_reflection_slice_writer(self):
        self.reject_extra('csr_regfile.sv',"always_comb rvfi_csr_o.pmpcfg_q[0].reserved = '1;")

    def test_additional_probe_output_override(self):
        self.reject_extra('cva6_rvfi_probes.sv',"always_comb rvfi_probes_o.csr.pmpcfg_q = '1;")

    def test_additional_probe_input_override(self):
        self.reject_extra('cva6_rvfi_probes.sv',"always_comb csr.pmpcfg_q = '1;")

    def test_second_connected_driver(self):
        self.reject_extra('cva6.sv','evil u(.output_o(pmpcfg));')

    def test_consumer_slice_override(self):
        self.reject_extra('load_store_unit.sv',"always_comb pmpcfg_i[0].locked = '1;")

    def test_additional_q_blocking_assignment(self):
        self.reject_extra('csr_regfile.sv',"always_comb pmpcfg_q[0].reserved = '1;")

    def test_second_consumer_driver(self):
        self.reject_extra('load_store_unit.sv','evil u(.output_o(pmpcfg_i));')


if __name__=='__main__':unittest.main()
