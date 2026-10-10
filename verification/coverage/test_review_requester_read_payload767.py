import unittest
import review_requester_read_payload767 as p


class Source(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.source=p.REQUESTER.read_text();cls.package=p.PACKAGE.read_text()
    def reject(self,source,package=None):
        with self.assertRaises(ValueError):p.source_contract(source,package or self.package)
    def test_actual(self):self.assertEqual(p.source_contract(self.source,self.package)['write_indices'],list(range(9,14)))
    def test_read_default(self):self.reject(self.source.replace("operand_payload[requester_index] = '0;","operand_payload[requester_index] = '1;"))
    def test_read_wdata_override(self):self.reject(self.source.replace("default: '0 // this is a read operation","wdata: alu_result_wdata_i, default: '0"))
    def test_partial_override(self):self.reject(self.source+"\nalways_comb operand_payload[0].be = alu_result_be_i;\n")
    def test_write_alias(self):self.reject(self.source.replace('operand_payload[NrOperandQueues + VFU_Alu]','operand_payload[0]'))
    def test_port_count(self):self.reject(self.source,self.package.replace('NrOperandQueues = 9;','NrOperandQueues = 10;'))
    def test_vfu_reorder(self):self.reject(self.source,self.package.replace('VFU_Alu, VFU_MFpu','VFU_MFpu, VFU_Alu'))
    def test_extra_output_writer(self):self.reject(self.source.replace('.data_i ({operand_payload[','.data_o (operand_payload['))


if __name__=='__main__':unittest.main()
