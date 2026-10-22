from pathlib import Path
import subprocess
import unittest


class SelectionTest(unittest.TestCase):
    def test_native_empty_element_and_extra_selection(self):
        hook = Path(__file__).with_name("diagnose_operand_hierarchy_v3.tcl")
        script = """
set oph3_library_only 1
source {%s}
set selected [list ""]
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {error "Empty must not be unselected"}
    if {[lsearch -exact $args -select] < 0} {error "Toggle prohibited"}
    set ::selected [lindex $args end]
}
if {[oph2_select {ara_tb.gen[0]}] ne {ara_tb.gen[0]}} {error "Selection failed"}
rename gui_list_select good_select
proc gui_list_select {args} {set ::selected {wanted extra}}
set selected {}
if {![catch {oph2_select wanted}]} {error "Extra selection accepted"}
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
