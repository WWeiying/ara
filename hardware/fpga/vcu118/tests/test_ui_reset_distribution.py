import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from ui_reset_fpga import OLD, NEW, patch_ui_reset_distribution


class UiResetTests(unittest.TestCase):
    def test_reject_drift_and_duplicate(self):
        source = "  logic ui_resetn;\n" + OLD
        after = patch_ui_reset_distribution(source)
        self.assertIn(NEW, after)
        self.assertIn("logic ui_resetn_sync;", after)
        for invalid in ("", source*2, after):
            with self.assertRaises(RuntimeError):
                patch_ui_reset_distribution(invalid)

    def test_exported_block_matches_transform(self):
        path = HERE.parents[1] / "ara_dsa_vcu118/rtl/board/dram_wrapper_xilinx.sv"
        current = path.read_text()
        original = current.replace("\n  logic ui_resetn_sync;", "").replace(NEW, OLD)
        self.assertEqual(patch_ui_reset_distribution(original), current)
        self.assertNotIn("ASYNC_REG =", NEW)
        self.assertNotIn("DONT_TOUCH", NEW)


if __name__ == "__main__":
    unittest.main()
