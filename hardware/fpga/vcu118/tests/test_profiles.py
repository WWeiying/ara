"""Profile packaging and Tcl regression entry point, without vendor synthesis."""
import pathlib
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPORT = ROOT.parent / "ara_dsa_vcu118"
SCRIPTS = (
    "config.tcl", "common.tcl", "constraint_checks.tcl", "create_project.tcl",
    "create_ip.tcl", "run_support.tcl", "run.ps1", "create_profile.ps1", "prepare_profile.tcl",
    "write_profile_bit.ps1", "write_profile_bit.tcl", "audit_routed.ps1",
)


class Profiles(unittest.TestCase):
    def test_exported_copies(self):
        for name in SCRIPTS:
            with self.subTest(name=name):
                self.assertEqual((ROOT / "scripts" / name).read_bytes(),
                                 (EXPORT / "scripts" / name).read_bytes())

    def test_board_interfaces(self):
        board = ET.parse(EXPORT / "board_files/vcu118/2.4/board.xml")
        interfaces = {element.attrib.get("name") for element in board.iter("interface")}
        self.assertTrue({"ddr4_sdram_c1_062", "ddr4_sdram_c2_062"} <= interfaces)

    def test_tcl(self):
        with tempfile.TemporaryDirectory(prefix="ara-profiles-") as temp:
            for name in ("test_profiles.tcl", "test_profiles_prepare.tcl",
                         "test_profiles_boundary.tcl", "test_profiles_bit.tcl"):
                result = subprocess.run(
                    ["tclsh", str(ROOT / "tests" / name), str(pathlib.Path(temp) / name)],
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
