from pathlib import Path
import subprocess
import unittest


class ProbeTests(unittest.TestCase):
    def tcl(self, body):
        hook = Path(__file__).with_name("diagnose_operand_hierarchy_v2.tcl")
        result = subprocess.run(["tclsh"], input="set oph2_library_only 1\nsource {%s}\n%s\nputs PASS\n" % (hook, body),
                                text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)

    def test_restore_expands_and_processes_events(self):
        self.tcl("""
set calls {}
foreach cmd {gui_covtable_show gui_covtable_setroot gui_list_expand gui_process_events} {
    proc $cmd {args} {lappend ::calls [list [lindex [info level 0] 0] $args]}
}
oph2_fullroot
if {[lindex [lindex $calls 2] 0] ne "gui_list_expand" || [lindex [lindex $calls 3] 0] ne "gui_process_events"} {error "Ordering differs"}
""")

    def test_selection_is_explicit_and_rejects_extra(self):
        self.tcl("""
set selected {other extra}
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {}; return}
    if {[lsearch -exact $args -select] < 0} {error "Toggle prohibited"}
    set ::selected [lindex $args end]
}
if {[oph2_select wanted] ne "wanted"} {error "Exact selection failed"}
rename gui_list_select good_select
proc gui_list_select {args} {set ::selected {wanted extra}}
if {![catch {oph2_select wanted}]} {error "Extra selection accepted"}
""")

    def test_cleanup_attempts_all_steps_after_failures(self):
        self.tcl("""
set env(OPH_MODE) full
set op1144_scopes x
set calls {}
proc gui_cov_show_value {args} {lappend ::calls display; error failed}
proc gui_exclusion {args} {lappend ::calls reset}
proc oph2_fullroot {} {lappend ::calls root; error failed}
proc oph2_query_all {args} {lappend ::calls query; error failed}
proc op1144_audit {args} {lappend ::calls audit; error failed}
proc op1144_save {args} {lappend ::calls save}
set errors [oph2_cleanup]
if {$calls ne {display reset root query audit save} || [llength $errors] != 4} {error "Cleanup was short circuited"}
""")


if __name__ == "__main__":
    unittest.main()
