import subprocess
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
MOCK = r'''
set chosen {}
set first_calls 0
set stuck 0
proc gui_list_get_selected {args} {
    global chosen first_calls
    if {[lsearch -exact $args -count] >= 0} {return [llength $chosen]}
    if {[lsearch -exact $args -first] >= 0} {
        incr first_calls
        return [list [list [lindex $chosen 0]]]
    }
    if {[lsearch -exact $args -flat] >= 0} {return $chosen}
    error "Unexpected native query"
}
proc gui_list_select {args} {
    global chosen stuck
    if {[lsearch -exact $args -unselect] >= 0} {
        if {!$stuck} {set chosen [lrange $chosen 1 end]}
        return
    }
    set index [lsearch -exact $args -select]
    if {$index < 0} {error "Unexpected selection operation"}
    set chosen [lindex $args [expr {$index + 1}]]
}
'''


class NativeSelectionTest(unittest.TestCase):
    def run_tcl(self, body):
        script = 'source {%s}\n' % (HERE / "capture_lzc_singleton.tcl")
        script += MOCK + '\nif {[catch {\n' + body + '\n} result]} {puts stderr $result; exit 1}\nputs CASE_PASS\n'
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CASE_PASS", result.stdout)

    def test_empty_selection_never_queries_wrapped_first(self):
        self.run_tcl('lzc_single_select {}\nif {$first_calls != 0} {error "Queried empty first"}')

    def test_multiple_selected_are_cleared_then_exact_target_selected(self):
        self.run_tcl('set chosen {00 10}\nlzc_single_select {01}\nif {$first_calls != 2 || $chosen ne {01}} {error "Wrong cleanup"}')

    def test_nonprogress_fails_instead_of_looping(self):
        self.run_tcl('set chosen {00}\nset stuck 1\nset failed [catch {lzc_single_select {01}} msg]\nif {!$failed || $msg ne "Native deselection did not progress"} {error "Missing failure"}')


if __name__ == "__main__":
    unittest.main()
