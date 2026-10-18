"""Guard the VA/PA type boundary independently of the physical AXI width."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class VirtualAddressTypes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'hardware/src/vlsu/addrgen.sv').read_text()

    def test_architectural_width_is_not_physical_width(self):
        self.assertRegex(self.source, r'VAddrWidth\s*=\s*CVA6Cfg.VLEN')
        self.assertIn('typedef logic [VAddrWidth-1:0] vaddr_t;', self.source)

    def test_all_untranslated_storage_is_virtual(self):
        for name in ('addr', 'idx_final_vaddr_d', 'next_addr_strided_temp',
                     'lookahead_addr_e_d', 'lookahead_addr_se_d',
                     'aligned_start_addr_d', 'aligned_next_start_addr_d', 'aligned_end_addr_d'):
            self.assertRegex(self.source, r'\bvaddr_t\s+' + name + r'\b')
        self.assertRegex(self.source, r'\.T\(vaddr_t\)\s*\) i_addrgen_idx_op_spill_reg')

    def test_burst_page_arithmetic_keeps_virtual_upper_bits(self):
        body = self.source.split('function automatic void set_end_addr (', 1)[1].split('endfunction', 1)[0]
        self.assertNotIn('AxiAddrWidth', body)
        self.assertNotIn('axi_addr_t', body)
        self.assertIn('aligned_start_addr[VAddrWidth-1:12]', body)
        self.assertIn('addr[VAddrWidth-1:OffsetWidth]', body)

    def test_physical_selection_still_follows_translation(self):
        self.assertIn('paddr = (en_ld_st_translation_i) ? mmu_paddr_i : axi_addrgen_q.addr;', self.source)
        self.assertIn('idx_final_paddr = (en_ld_st_translation_i) ? mmu_paddr_i : idx_final_vaddr_q;', self.source)
        self.assertIn('!mmu_exception_i.valid', self.source)

    def test_exception_queue_retains_virtual_address(self):
        package = (ROOT / 'hardware/include/ara_pkg.sv').read_text()
        self.assertRegex(package, r'axi_pkg::largest_addr_t vaddr;')
        self.assertIn('mmu_exception_d.tval = axi_addrgen_q.addr;', self.source)
        self.assertIn('addrgen_exception_o.tval  = idx_final_vaddr_q;', self.source)


if __name__ == '__main__':
    unittest.main()
