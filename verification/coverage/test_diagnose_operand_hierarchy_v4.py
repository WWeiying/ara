from pathlib import Path
import subprocess
import unittest


class RealSelectionTest(unittest.TestCase):
    def test_exact_native_nested_shape(self):
        hook = Path(__file__).with_name("diagnose_operand_hierarchy_v4.tcl")
        script = """
set oph4_library_only 1
source {%s}
set scope {ara_tb.gen_lanes[0].alu_a}
if {[oph4_tokens {{}}] ne {}} {error "Empty group rejected"}
if {[lindex [oph4_tokens [list [list $scope]]] 0] ne $scope} {error "Native token not decoded"}
if {![catch {oph4_tokens {{a b}}}]} {error "Multiple tokens accepted"}
if {![catch {oph4_tokens {{a} {b}}}]} {error "Multiple groups accepted"}
set selected {{}}
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {{}}; return}
    if {[lsearch -exact $args -select] < 0} {error "Toggle prohibited"}
    set ::selected [list [lindex $args end]]
}
if {[oph2_select $scope] ne $scope} {error "Explicit selection failed"}
if {[oph2_select other] ne "other"} {error "Previous selection not cleared"}
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
