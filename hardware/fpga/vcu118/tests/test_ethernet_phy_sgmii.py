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
if {![catch {eth_sgmii::pcs_read test 2}]} {error "PCS identifier access accepted"}
""")
        self.assertEqual(output.splitlines(), [
            "COMMAND 508 0000001f", "COMMAND 504 030d4800",
            "COMMAND 508 000000d3", "COMMAND 504 030e4800",
            "COMMAND 508 0000401f", "COMMAND 504 030d4800",
            "COMMAND 508 00004000", "COMMAND 504 030e4800",
        ])

    def test_pcs_pulse_releases_request_on_error(self):
        output = self.tcl("""
set ::request_state 0
set ::phy_ok 1
proc get_hw_probes {args} { return {pcs_request} }
proc get_property {key probe} {
    if {$key eq "NAME"} { return pcs_request }
    if {$key eq "TYPE"} { return vio_output }
    error "unexpected property $key"
}
proc set_property {key value probe} { set ::request_state $value }
proc commit_hw_vio {vio} {}
proc refresh_hw_vio {args} {}
rename eth_board::probe_value eth_board::real_probe_value
proc eth_board::probe_value {vio name type property width} {
    if {$name eq "pcs_request"} { return $::request_state }
    if {$name eq "phy_rst_n_OBUF"} { return $::phy_ok }
    error "unexpected probe $name"
}
eth_sgmii::pulse_pcs_reset vio
if {$::request_state != 0} {error "request left asserted"}
set ::phy_ok 0
if {![catch {eth_sgmii::pulse_pcs_reset vio} message] ||
    ![string match {*external PHY reset changed*} $message]} {
    error "unexpected failure result: $message"
}
if {$::request_state != 0} {error "request left asserted after failure"}
puts PCS_PULSE_CLEANUP_PASS
""")
        self.assertIn("PCS_RESET_PULSE_COMPLETE", output)
        self.assertIn("PCS_PULSE_CLEANUP_PASS", output)


if __name__ == "__main__":
    unittest.main()
