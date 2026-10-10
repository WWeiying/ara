import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

import apply_operand_1144_690 as app


class ApplicationTests(unittest.TestCase):
    def test_external_qualification_seal_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                app.prepare(Path(directory) / "unused", "0"*64)

    def test_summary_reset_and_unrelated_metrics_are_strict(self):
        raw = {"queue": dict(Name="queue", Depth="0", Score="10%", Branch="20%", Line="30%")}
        changed = copy.deepcopy(raw)
        changed["queue"].update(Branch="40%", Score="20%")
        self.assertEqual(len(app.summary_deltas(raw, changed, raw, ["queue"])), 2)
        for bad, reset, scopes in ((changed, {}, ["queue"]), (changed, raw, ["other"]), (raw, raw, ["queue"])):
            with self.assertRaises(ValueError):
                app.summary_deltas(raw, bad, reset, scopes)
        changed["queue"]["Line"] = "31%"
        with self.assertRaises(ValueError):
            app.summary_deltas(raw, changed, raw, ["queue"])

    def test_summary_hierarchy_rejects_duplicate_or_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.csv"
            header = "Name,Depth,Score,Line,Toggle,FSM,Condition,Branch\n"
            for body in ("queue,2,1,1,1,1,1,1\n", "queue,0,1,1,1,1,1,1\nqueue,0,1,1,1,1,1,1\n"):
                path.write_text(header+body)
                with self.assertRaises(ValueError):
                    app.summaries(path)

    def run_tcl_session(self, count=690, bad=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "live-ready").write_text("verified\n")
            (root / "selection.tcl").write_text(
                "set op1144_design {/design}\nset op1144_test {/unused}\nset op1144_scopes {queue}\n"
                "array set op1144_keys {queue {4,0 4,1}}\narray set op1144_targets {queue {4,0}}\n"
                "set opapp_databases {%s}\nset opapp_tests {%s}\nset opapp_native {/sealed/first.el}\n" %
                (" ".join("/db%d" % n for n in range(count)), " ".join("/test%d" % n for n in range(count))))
            script = '''set opapp_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(OP1144_BASE_HOOK) {%s}
opapp_load
set selection {}
set active 0
set bad %d
proc gui_open_cov {args} {
    set ::opened [llength [lindex $args 5]]
}
proc gui_get_window_ids {} {return CoverageTable.1}
proc gui_covdetail_query {args} {return Branch}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_action {args} {}
proc gui_list_expand {args} {}
proc gui_list_get_selected {args} {return $::selection}
proc gui_list_select {args} {
    if {[lindex $args 4] eq "-unselect"} {set ::selection {}} else {set ::selection [lindex $args 5]}
}
proc gui_list_get_property {args} {
    set index [lindex $args 3]
    if {$index > 10} {error end}
    return [lindex {Score Line Toggle FSM Condition Branch} [expr {$index-5}]]
}
proc gui_list_get {args} {
    set id [lindex $args 1]
    set op [lindex $args 2]
    set item [lindex $args 3]
    if {$id eq "CoverageTable.1"} {
        switch -- $op {
            -firstChild {if {$item eq ""} {return Q}; return 0}
            -nextSibling {return 0}
            -text {if {$item == 0} {return queue}; if {$item == 5 || $item == 10} {return "$::active.00%%"}; return 0.00%%}
        }
    }
    switch -- $op {
        -firstChild {if {$item eq ""} {return P}; if {$item eq "P"} {return L0}; return 0}
        -nextSibling {if {$item eq "L0"} {return L1}; return 0}
        -path {if {$item eq "P"} {return Item4}; if {$item eq "L0"} {return Item4.Branch4.0}; return Item4.Branch4.1}
        -meta {if {$item eq "L0"} {return Branch4.0}; return Branch4.1}
        -childCount {return 0}
    }
    error "Unknown API"
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {set ::active 0; return}
    if {[lindex $args end] eq "-recalculate"} {return}
    if {[llength $::selection] != 1} {error "Not singleton"}
    return [expr {$::active && ($::bad || [lindex $::selection 0] eq "Branch4.0")}]
}
proc gui_exclusion_file {args} {
    if {[lindex $args 0] eq "-load"} {set ::active 1; return}
    set path [lindex [lindex $args 2] 0]
    set f [open $path w]
    if {$::active} {puts $f native}
    close $f
}
set failed [catch {opapp_session} message]
gui_exclusion -reset
if {[info exists op1144_scopes]} {op1144_audit final 0}
op1144_save final-empty.el 1
if {$failed} {puts "EXPECTED_REJECT $message"; exit 3}
puts "FULL_APPLICATION_PASS $::opened"
''' % (app.TCL, root, app.HERE / "capture_operand_1144.tcl", int(bad))
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, cwd=directory)
            self.assertEqual((root / "final-empty.el").read_bytes(), b"")
            if result.returncode == 0:
                self.assertEqual(len((root / "selected_tests.txt").read_text().splitlines()), 690)
                raw = app.summaries(root / "summary_raw.csv")
                applied = app.summaries(root / "summary_applied.csv")
                reset = app.summaries(root / "summary_reset.csv")
                self.assertTrue(app.summary_deltas(raw, applied, reset, ["queue"]))
                for name in ("initial-empty.el", "reset-empty.el"):
                    self.assertEqual((root / name).read_bytes(), b"")
            return result

    def test_full690_proc_source_raw_applied_reset_lifecycle(self):
        result = self.run_tcl_session()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn("FULL_APPLICATION_PASS 690", result.stdout)

    def test_single_seed_rejected_before_opening_cov(self):
        result = self.run_tcl_session(count=1)
        self.assertEqual(result.returncode, 3, result.stdout+result.stderr)
        self.assertIn("Requires exact690", result.stdout)

    def test_neighbor_exclusion_rejected_and_final_reset(self):
        result = self.run_tcl_session(bad=True)
        self.assertEqual(result.returncode, 3, result.stdout+result.stderr)
        self.assertIn("Singleton exclusion state differs", result.stdout)


if __name__ == "__main__":
    unittest.main()
