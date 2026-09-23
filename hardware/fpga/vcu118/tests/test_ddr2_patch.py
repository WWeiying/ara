#!/usr/bin/env python3
"""Source-patch checks against the reviewed single-DDR wrapper."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from ddr2_fpga import patch_ddr2


def baseline_wrapper():
    return subprocess.check_output([
        "git", "show", "d8fee8a9:hardware/fpga/ara_dsa_vcu118/rtl/board/dram_wrapper_xilinx.sv"
    ], cwd=HERE, text=True)


class DdrPatchTests(unittest.TestCase):
    def test_channel_and_reset(self):
        source = patch_ddr2(baseline_wrapper())
        self.assertIn("parameter int unsigned Channel = 0", source)
        self.assertEqual(source.count("  ddr4_c2 i_dram ("), 1)
        self.assertEqual(source.count("  ddr4 i_dram ("), 2)
        self.assertIn(".rst_ni(fabric_ready_o & fabric_reset_ni)", source)
        self.assertNotIn(".rst_ni(fabric_ready_o & soc_resetn_i)", source)
        self.assertIn("`ifdef ARA_FPGA_DDR2\n  input  logic  fabric_reset_ni,\n`endif", source)
        self.assertEqual(source.count(".c0_ddr4_aresetn            ( ui_resetn    )"), 3)
        self.assertNotIn(".c1_ddr4", source)

    def test_ready_generation_is_independent(self):
        original = baseline_wrapper()
        source = patch_ddr2(original)
        start = "  logic ui_por_n;"
        end = "  rstgen i_ui_rstgen ("
        self.assertEqual(source[source.index(start):source.index(end)],
                         original[original.index(start):original.index(end)])
        self.assertEqual(source.count(".sys_rst                    ( sys_rst_i    )"), 3)

    def test_reject_drift_and_duplicate_application(self):
        original = baseline_wrapper()
        for source in ("", original * 2, patch_ddr2(original),
                       original.replace(".rst_ni(fabric_ready_o)", ".rst_ni(other)"),
                       original.replace("  ddr4 i_dram (", "  changed i_dram (")):
            with self.subTest(source=source[:40]):
                with self.assertRaises(RuntimeError):
                    patch_ddr2(source)

    def test_exported_copies(self):
        package = HERE.parent / "ara_dsa_vcu118"
        for template, exported in (("rtl/ara_ddr_router.sv", "rtl/board/ara_ddr_router.sv"),
                                   ("constraints/cdc.xdc", "constraints/cdc.xdc")):
            self.assertEqual((HERE / template).read_bytes(), (package / exported).read_bytes())

    def test_exported_wrapper(self):
        wrapper = HERE.parent / "ara_dsa_vcu118/rtl/board/dram_wrapper_xilinx.sv"
        self.assertEqual(wrapper.read_bytes(), patch_ddr2(baseline_wrapper()).encode())


if __name__ == "__main__":
    unittest.main()
