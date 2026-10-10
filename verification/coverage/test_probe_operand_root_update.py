from pathlib import Path
import subprocess
import unittest


class RootContractTest(unittest.TestCase):
    def test_relative_root_identity_and_negative_alias(self):
        hook = Path(__file__).with_name("probe_operand_root_update.tcl")
        script = """
set oph6_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) /not-used
set rootpath i_system
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {return handle7}
    if {[lsearch -exact $args -nextSibling] >= 0} {return ""}
    return $::rootpath
}
rename open real_open
proc open {args} {return fake}
rename puts real_puts
proc puts {args} {}
rename close real_close
proc close {args} {}
proc oph_write {stage scope handle} {set ::bound [list $stage $scope $handle]}
set scope ara_tb.dut.i_ara_soc.i_system
if {[oph6_root_row $scope rooted] ne "handle7" || $bound ne [list rooted $scope handle7]} {error "Local root not bound"}
set rootpath wrong
if {![catch {oph6_root_row $scope rooted}]} {error "Wrong local row accepted"}
rename puts muted_puts
rename real_puts puts
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
