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
if {![catch {eth_sgmii::mdio_write test 20 0x29c7}]} {error "unguarded CFG2 write accepted"}
if {![catch {eth_sgmii::real_axi_write test 0x508 0x4140}]} {error "raw data write accepted"}
if {![catch {eth_sgmii::real_axi_write test 0x504 0x03004800}]} {error "raw BMCR command accepted"}
if {![catch {eth_sgmii::real_axi_write test 0x504 0x03144800}]} {error "raw CFG2 command accepted"}
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

    def test_sgmii_aneg_restart_restores_cfg2_on_failure(self):
        output = self.tcl("""
set ::cfg2 0x29c7
set ::fail_once 0
rename eth_sgmii::axi_write eth_sgmii::real_axi_write
proc eth_sgmii::axi_write {axi address value} {
    eth_sgmii::real_axi_write $axi $address $value
    if {$address == 0x508} { set ::data $value }
    if {$address == 0x504 && $value == 0x03144800} {
        set ::cfg2 $::data
        puts [format "CFG2_WRITE 0x%04x" $::cfg2]
        if {$::fail_once && ($::cfg2 & 0x80) == 0} {
            set ::fail_once 0
            error "injected failure after CFG2 disable"
        }
    }
}
proc get_property {name object} {
    if {$name eq "CMD.SIZE"} {return 32}
    if {$name eq "CMD.LEN"} {return 1}
    if {$name eq "STATUS.AXI_WRITE_BUSY"} {return 0}
    if {$name eq "STATUS.AXI_WRITE_DONE"} {return 1}
    if {$name eq "STATUS.BRESP"} {return OKAY}
    error "unexpected property $name"
}
proc create_hw_axi_txn {args} {return txn}
proc run_hw_axi {txn} {}
proc refresh_hw_axi {axi} {}
proc delete_hw_axi_txn {txn} {}
rename eth_board::mdio_ready eth_board::real_mdio_ready
proc eth_board::mdio_ready {axi} {}
rename eth_sgmii::mdio_read eth_sgmii::real_mdio_read
proc eth_sgmii::mdio_read {axi reg} {
    if {$reg != 20} {error "unexpected register"}
    return $::cfg2
}
eth_sgmii::restart_sgmii_aneg test $::cfg2
if {$::cfg2 != 0x29c7 || $eth_sgmii::cfg2_allowed ne {}} {error "CFG2 not restored"}
set ::fail_once 1
if {![catch {eth_sgmii::restart_sgmii_aneg test $::cfg2} message] ||
    $message ne "injected failure after CFG2 disable"} {error "failure not propagated: $message"}
if {$::cfg2 != 0x29c7 || $eth_sgmii::cfg2_allowed ne {}} {error "CFG2 not restored after failure"}
puts CFG2_RESTORE_PASS
""")
        self.assertIn("SGMII_ANEG_RESTARTED CFG2=0x29c7", output)
        self.assertEqual(output.count("CFG2_WRITE 0x2947"), 2)
        self.assertEqual(output.count("CFG2_WRITE 0x29c7"), 2)
        self.assertIn("CFG2_RESTORE_PASS", output)


if __name__ == "__main__":
    unittest.main()
