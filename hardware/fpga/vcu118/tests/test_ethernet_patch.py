"""Fail closed if the integration patch or profile boundaries drift."""
import unittest
from test_ddr2_patch import HERE, baseline_wrapper, patch_ddr2
from ddr_cut_fpga import patch_ddr_read_cut
from ethernet_fpga import patch_ethernet


class EthernetPatchTests(unittest.TestCase):
    def original(self):
        return patch_ddr_read_cut(patch_ddr2(baseline_wrapper()))

    def test_export_matches(self):
        wrapper = HERE.parent / "ara_dsa_vcu118/rtl/board/dram_wrapper_xilinx.sv"
        self.assertEqual(wrapper.read_text(), patch_ethernet(self.original()))

    def test_patch_guards(self):
        text = self.original()
        for invalid in ("", text * 2, patch_ethernet(text),
                        text.replace("// PHY interfaces", "// changed PHY interface")):
            with self.subTest(source=invalid[:30]), self.assertRaises(RuntimeError):
                patch_ethernet(invalid)

    def test_preserves_mig_cut_and_flag_off_path(self):
        text = patch_ethernet(self.original())
        self.assertIn("assign cdc_cut_req = cdc_ara_req;", text)
        self.assertIn("assign cdc_ara_rsp = cdc_cut_rsp;", text)
        self.assertEqual(text.count("i_eth_shared_ddr ("), 1)
        self.assertEqual(text.count("i_eth_loader ("), 1)
        self.assertIn(".mem_req_o(cdc_cut_req)", text)
        self.assertIn(".ara_req_i(cdc_ara_req)", text)
        self.assertEqual(text.count("ddr4 i_dram ("), self.original().count("ddr4 i_dram ("))


if __name__ == "__main__":
    unittest.main()
