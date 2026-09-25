from pathlib import Path
import shutil
import subprocess
import unittest


ETHERNET = Path(__file__).resolve().parents[1] / "ethernet"


@unittest.skipUnless(shutil.which("tclsh"), "tclsh unavailable")
class PhySgmiiTests(unittest.TestCase):
    def tcl(self, body):
        script = ("set ::eth_sgmii_library_only 1\n"
                  f"source {{{(ETHERNET / 'phy_sgmii.tcl').as_posix()}}}\n"
                  + body)
        return subprocess.run(["tclsh"], input=script, text=True,
                              capture_output=True, check=True).stdout

    def test_write_commands_and_whitelist(self):
        output = self.tcl("""
rename eth_sgmii::axi_write eth_sgmii::real_axi_write
proc eth_sgmii::axi_write {axi address value} {
    puts [format "COMMAND %x %08x" $address $value]
}
rename eth_board::mdio_ready eth_board::real_mdio_ready
proc eth_board::mdio_ready {axi} {}
eth_sgmii::mdio_write test 13 0x001f
eth_sgmii::mdio_write test 14 0x00d3
eth_sgmii::mdio_write test 13 0x401f
eth_sgmii::mdio_write test 14 0x4000
if {![catch {eth_sgmii::mdio_write test 0 0x4000}]} {error "BMCR write accepted"}
if {![catch {eth_sgmii::mdio_write test 14 0x4140}]} {error "loopback write accepted"}
if {![catch {eth_sgmii::real_axi_write test 0x508 0x4140}]} {error "raw data write accepted"}
if {![catch {eth_sgmii::real_axi_write test 0x504 0x03004800}]} {error "raw BMCR command accepted"}
""")
        self.assertEqual(output.splitlines(), [
            "COMMAND 508 0000001f", "COMMAND 504 030d4800",
            "COMMAND 508 000000d3", "COMMAND 504 030e4800",
            "COMMAND 508 0000401f", "COMMAND 504 030d4800",
            "COMMAND 508 00004000", "COMMAND 504 030e4800",
        ])


if __name__ == "__main__":
    unittest.main()
