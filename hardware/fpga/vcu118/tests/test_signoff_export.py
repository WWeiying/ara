"""Check imported dependency bytes and retained board-specific export inputs."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
PACKAGE = HERE.parent / "ara_dsa_vcu118"
sys.path.insert(0, str(HERE))
from axi_remap_fpga import patch_axi_remap
from export import patch_sram_cache


class SignoffExportTests(unittest.TestCase):
    def test_addrgen_preserves_main_virtual_address_repair(self):
        relative = 'rtl/ara/hardware/src/vlsu/addrgen.sv'
        source = (ROOT / 'hardware/src/vlsu/addrgen.sv').read_bytes()
        self.assertEqual(source, (PACKAGE / relative).read_bytes())
        manifest = json.loads((PACKAGE / 'manifest.json').read_text())
        record = next(row for row in manifest['source_hashes_before_integration']
                      if row['file'] == relative)
        self.assertEqual(hashlib.sha256(source).hexdigest(), record['source_sha256'])

    def test_registered_dependencies_retain_only_reviewed_fpga_transforms(self):
        manifest = json.loads((PACKAGE / "manifest.json").read_text())
        transforms = {
            "rtl/axi/src/axi_id_remap.sv": patch_axi_remap,
            "rtl/cva6/common/local/util/sram_cache.sv": patch_sram_cache,
        }
        checked = {name: 0 for name in ("axi", "cva6", "fpnew", "fpu_div_sqrt_mvp")}
        for record in manifest["source_hashes_before_integration"]:
            relative = Path(record["file"])
            if relative.parts[1] not in checked:
                continue
            source = ROOT / "hardware/deps" / Path(*relative.parts[1:])
            raw = source.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["source_sha256"], str(relative))
            expected = transforms.get(relative.as_posix(), lambda text: text)(raw.decode())
            self.assertEqual((PACKAGE / relative).read_bytes(), expected.encode(), str(relative))
            checked[relative.parts[1]] += 1
        self.assertTrue(all(count > 0 for count in checked.values()), checked)

    def test_dual_ddr_clock_and_build_inputs_are_reproducible(self):
        for source, destination in (
            ("rtl/ara_dsa_vcu118.sv", "rtl/board/ara_dsa_vcu118.sv"),
            ("constraints/ddr2_clock.xdc", "constraints/ddr2_clock.xdc"),
            ("scripts/create_project.tcl", "scripts/create_project.tcl"),
            ("scripts/close_routed_setup.tcl", "scripts/close_routed_setup.tcl"),
        ):
            self.assertEqual((HERE / source).read_bytes(),
                             (PACKAGE / destination).read_bytes(), source)
        board = (PACKAGE / "rtl/board/ara_dsa_vcu118.sv").read_text()
        self.assertIn(".dram_clk_i(c2_sys_clk)", board)
        self.assertIn("i_bufds_c2_clk", board)
        self.assertIn("constraints ddr2_clock.xdc",
                      (PACKAGE / "scripts/create_project.tcl").read_text())


if __name__ == "__main__":
    unittest.main()
