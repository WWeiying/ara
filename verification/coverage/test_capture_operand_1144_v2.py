from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_operand_1144_v2 as v2
from test_capture_operand_1144 import CaptureTests


class ScopeTests(unittest.TestCase):
    def run_session(self, hook):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test = root / "code.vdb"
            (test / "snps/coverage/db/testdata/sample").mkdir(parents=True)
            (root / "live-ready").write_text("verified\n")
            (root / "selection.tcl").write_text(
                'set op1144_design {/design}\nset op1144_test {%s}\n'
                'set op1144_scopes {queue}\narray set op1144_keys {queue {4,0 4,1}}\n'
                'array set op1144_targets {queue {4,0}}\n' % test)
            script = '''set op1144_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set selection {}
set active 0
proc gui_open_cov {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Branch}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_expand {args} {}
proc gui_list_get_selected {args} {return $::selection}
proc gui_list_select {args} {
    if {[lindex $args 4] eq "-unselect"} {set ::selection {}} else {set ::selection [lindex $args 5]}
}
proc gui_list_get {args} {
    set op [lindex $args 2]
    set item [lindex $args 3]
    switch -- $op {
        -firstChild {if {$item eq ""} {return P}; if {$item eq "P"} {return L0}; return 0}
        -nextSibling {if {$item eq "L0"} {return L1}; return 0}
        -path {if {$item eq "P"} {return Item4}; if {$item eq "L0"} {return Item4.Branch4.0}; return Item4.Branch4.1}
        -meta {if {$item eq "L0"} {return Branch4.0}; return Branch4.1}
        -childCount {return 0}
        default {error "Unknown API"}
    }
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {set ::active 0; return}
    if {[lindex $args end] eq "-recalculate"} {return}
    if {[llength $::selection] != 1} {error "Not singleton"}
    return [expr {$::active && [lindex $::selection 0] eq "Branch4.0"}]
}
proc gui_exclude_items {args} {set ::active 1}
proc gui_exclusion_file {args} {
    if {[lindex $args 0] eq "-load"} {set ::active 1; return}
    set path [lindex [lindex $args 2] 0]
    set f [open $path w]
    if {$::active} {puts $f native}
    close $f
}
if {[catch {op1144_session} message]} {puts "SESSION_FAILED $message"; exit 3}
proc check_globals {} {
    global op1144_keys op1144_targets op1144_design op1144_test op1144_scopes
    if {$op1144_keys(queue) ne "4,0 4,1" || $op1144_targets(queue) ne "4,0" ||
        $op1144_design ne "/design" || $op1144_scopes ne "queue" || $op1144_test eq ""} {error "Global scope differs"}
    array set seen [op1144_metadata queue]
    if {[array size seen] != 2} {error "Metadata cannot read global keys"}
}
if {[catch {check_globals} message]} {puts "GLOBAL_FAILED $message"; exit 4}
gui_exclusion -reset
op1144_audit final 0
op1144_save final-empty.el 1
puts FULL_SESSION_SCOPE_PASS
''' % (hook, root)
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
            if result.returncode == 0:
                for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
                    self.assertEqual((root / name).read_bytes(), b"")
                self.assertEqual((root / "first.el").read_bytes(), (root / "second.el").read_bytes())
            return result

    def test_original_scope_bug_is_reproduced(self):
        result = self.run_session(v2.ORIGINAL_TCL)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('op1144_keys(queue)', result.stdout)

    def test_proc_source_exposes_all_globals_to_metadata_and_roundtrip(self):
        result = self.run_session(v2.original.TCL)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FULL_SESSION_SCOPE_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
