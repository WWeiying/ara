import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from axi_remap_fpga import ORIGINAL, LOCAL_COUNTERS, patch_axi_remap, restore_axi_remap


class PatchTest(unittest.TestCase):
    def test_roundtrip(self):
        source = "prefix\n" + ORIGINAL + "suffix\n"
        self.assertEqual(restore_axi_remap(patch_axi_remap(source)), source)

    def test_context_changes_rejected(self):
        for text in ("", ORIGINAL * 2, LOCAL_COUNTERS, ORIGINAL.replace("+= 1", "+= 2")):
            with self.assertRaises(RuntimeError):
                patch_axi_remap(text)

    def test_exported_source(self):
        path = Path(__file__).resolve().parents[2] / "ara_dsa_vcu118/rtl/axi/src/axi_id_remap.sv"
        source = path.read_text()
        self.assertEqual(patch_axi_remap(restore_axi_remap(source)), source)


if __name__ == "__main__":
    unittest.main()
