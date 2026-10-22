from pathlib import Path
import subprocess
import tempfile
import unittest

import apply_operand_1144_690_v2 as app
import test_apply_operand_1144_690 as previous


class SummaryTests(unittest.TestCase):
    def test_external_seal(self):
        previous.ApplicationTests().test_external_qualification_seal_required()

    def test_summary_deltas(self):
        previous.ApplicationTests().test_summary_reset_and_unrelated_metrics_are_strict()

    def test_summary_hierarchy(self):
        previous.ApplicationTests().test_summary_hierarchy_rejects_duplicate_or_gap()


class CallingContextTests(unittest.TestCase):
    def run_context(self, hook, partial_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "DVEfiles").mkdir()
            # Reuse the exact generated selection which failed on real DVE.
            (root / "selection.tcl").write_bytes((app.FAILED / "selection.tcl").read_bytes())
            (root / "live-ready").write_text("verified\n")
            script = '''set opapp_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(OP1144_BASE_HOOK) {%s}
opapp_load
set inject %d
set active 0
proc gui_open_cov {args} {
    set directories [lindex $args 3]
    set tests [lindex $args 5]
    # DVE's failed log contains literal braces. Validate the raw strings,
    # not Tcl llength/foreach which would hide that serialization defect.
    foreach value [list $directories $tests] {
        if {[string first "\\{" $value] >= 0 || [string first "\\}" $value] >= 0} {error "Literal element braces passed to DVE"}
        if {[llength [split $value " "]] != 690} {error "Not exactly690 raw API path tokens"}
    }
    foreach database [split $directories " "] {
        if {![file isdirectory $database]} {error "Literal path not a directory"}
    }
    set log [open [file join $::env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] w]
    puts $log "The design '$::op1144_design' was loaded successfully."
    if {$::inject} {puts $log "Warning: DVCDT136 Failed to load tests UCAPI-DLMA"}
    close $log
}
proc gui_get_window_ids {} {return CoverageTable.1}
proc gui_list_expand {args} {}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion {args} {if {[lindex $args 0] eq "-reset"} {set ::active 0}}
proc gui_exclusion_file {args} {
    if {[lindex $args 0] eq "-load"} {set ::active 1; return}
    set path [lindex [lindex $args 2] 0]
    set f [open $path w]
    if {$::active} {puts $f native}
    close $f
}
proc op1144_audit {stage wanted} {
    global active op1144_scopes op1144_keys op1144_targets
    if {$active != $wanted || [llength $op1144_scopes] != 36} {error "Scope/state lifecycle differs"}
    set total 0
    foreach scope $op1144_scopes {
        if {[llength $op1144_keys($scope)] != 101} {error "Global keys unavailable"}
        incr total [llength $op1144_targets($scope)]
    }
    if {$total != 1144} {error "Global targets differ"}
}
proc opapp_summary {stage} {
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) summary_$stage.csv] w]
    puts $f $::active
    close $f
}
set failed [catch {opapp_session} message]
gui_exclusion -reset
op1144_save final-empty.el 1
if {$failed} {puts "CONTEXT_REJECT $message"; exit 3}
puts FULL690_CALLING_CONTEXT_PASS
''' % (hook, root, app.HERE / "capture_operand_1144.tcl", int(partial_failure))
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, cwd=directory)
            files = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            self.assertEqual(files["final-empty.el"], b"")
            return result, files

    def test_original_generated_list_serialization_bug_reproduced(self):
        result, files = self.run_context(app.HERE / "apply_operand_1144_690.tcl")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("Literal element braces passed", result.stdout)
        self.assertIn("selected_tests.txt", files)
        self.assertNotIn("summary_raw.csv", files)

    def test_generated_selection_in_proc_passes_canonical_api_strings(self):
        result, files = self.run_context(app.original.TCL)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OPAPP_LOAD_GATE_PASSED", result.stdout)
        self.assertEqual(len(files["selected_tests.txt"].splitlines()), 690)
        self.assertEqual(files["summary_raw.csv"], files["summary_reset.csv"])
        self.assertNotEqual(files["summary_raw.csv"], files["summary_applied.csv"])

    def test_partial_load_error_blocks_selected_and_raw_even_with_table(self):
        result, files = self.run_context(app.original.TCL, partial_failure=True)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("GUI coverage load error", result.stdout)
        self.assertNotIn("selected_tests.txt", files)
        self.assertNotIn("summary_raw.csv", files)
        self.assertNotIn("applied.el", files)


if __name__ == "__main__":
    unittest.main()
