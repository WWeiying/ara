"""Static packaging checks, not functional or PPA acceptance."""
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class MeasurementWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = (ROOT / 'verification/akv/synthesis/akv_engine_synth_wrapper.sv').read_text()
        cls.new = (HERE / 'akv_engine_synth_wrapper.sv').read_text()

    def test_original_top_ports_unchanged(self):
        marker = 'module akv_engine_synth_wrapper import akv_engine_synth_types_pkg::*; ('
        for text in (self.old, self.new):
            self.assertEqual(text.count(marker), 1)
        header = lambda text: text.split(marker, 1)[1].split('\n  );', 1)[0]
        self.assertEqual(header(self.old), header(self.new))

    def test_original_package_constants_and_types_preserved(self):
        prefix = self.new.split('endpackage', 1)[0]
        for addition in (
            '`include "shared_reader_types.svh"\n',
            '  `QBS_AKV_SHARED_READER_TYPEDEF_REQ_T(shared_read_req_t, VAddrWidth)\n',
            '  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(shared_read_rsp_t, AxiDataWidth, VAddrWidth, exception_t)\n',
        ):
            self.assertEqual(prefix.count(addition), 1)
            prefix = prefix.replace(addition, '', 1)
        self.assertEqual(prefix, self.old.split('endpackage', 1)[0])

    def test_single_reader_and_explicit_endpoints(self):
        self.assertEqual(self.new.count('qbs_akv_shared_reader #('), 1)
        self.assertEqual(self.new.count('  akv_engine #('), 1)
        self.assertNotIn('qbs_read_engine #(', self.new)
        for connection in (
            "assign shared_req[0] = '0;",
            '.reader_req_o(shared_req[1]), .reader_rsp_i(shared_rsp[1])',
            '.reader_req_t(shared_read_req_t), .reader_rsp_t(shared_read_rsp_t)',
            '.client_req_i(shared_req), .client_rsp_o(shared_rsp)',
            ".owner_i({owner_q, 1'b0}), .command_fire_i({command_fire, 1'b0})",
        ):
            self.assertEqual(self.new.count(connection), 1)

    def test_owner_lifetime_uses_real_handshakes(self):
        for statement in (
            'assign command_fire = command_valid_i && command_ready_o;',
            "if (!rst_ni) owner_q <= 1'b0;",
            "if ((success_valid_o || fault_valid_o) && terminal_ready_i) owner_q <= 1'b0;",
            "if (command_fire) owner_q <= 1'b1;",
        ):
            self.assertEqual(self.new.count(statement), 1)
        self.assertNotIn('dut.', self.new)
        self.assertNotIn('.i_read_engine.', self.new)
        self.assertNotIn('force ', self.new)

    def test_functional_memory_ports_not_tied(self):
        block = self.new.split(') i_shared_reader (', 1)[1].split('\n  );', 1)[0]
        for ports in (
            '.core_st_pending_i, .en_ld_st_translation_i,',
            '.mmu_req_o, .mmu_vaddr_o, .mmu_is_store_o, .mmu_valid_i, .mmu_paddr_i,',
            '.mmu_exception_valid_i, .mmu_exception_i,',
            '.physical_check_valid_o, .physical_check_addr_o, .physical_check_bytes_o,',
            '.physical_range_allowed_i,',
            '.axi_ar_o, .axi_ar_valid_o, .axi_ar_ready_i,',
            '.axi_r_i, .axi_r_valid_i, .axi_r_ready_o',
        ):
            self.assertEqual(block.count(ports), 1)


if __name__ == '__main__':
    unittest.main()
