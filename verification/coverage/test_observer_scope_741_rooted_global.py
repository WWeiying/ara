import subprocess
import unittest

import observer_scope_741_rooted_global as adapter


class GlobalScopeTests(unittest.TestCase):
    def exercise(self, entry):
        script = '''
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
proc p740_save {name} {}
proc p740_root {} {}
set stages {}
proc p740_summary {stage} {
    global p740_scopes p740_root_names stages
    if {![info exists p740_scopes] || [llength $p740_scopes] != 8} {error "missing global roots"}
    foreach scope $p740_scopes {
        if {![info exists p740_root_names($scope)]} {error "missing global root name"}
    }
    lappend stages $stage
}
proc gui_exclude_items {args} {}
proc gui_exclusion {args} {}
proc gui_exclusion_file {args} {}
proc gui_cov_excl_review {args} {return 1}
if {[catch {apply_reviewed_waivers CoverageTable.1} message]} {puts stderr $message; exit 1}
if {$stages ne {raw applied reloaded reset}} {error "stage sequence differs"}
''' % (entry, adapter.HERE.parent / 'out/observer-only-rooted-741-agent-20261007-03')
        return subprocess.run(['tclsh'], input=script, text=True, capture_output=True)

    def test_scope_only_adapter(self):
        self.assertEqual(len(adapter.namespace()['TARGETS']), 4)

    def test_real_proc_globals_all_four_stages(self):
        result = self.exercise(adapter.HERE / 'observer_scope_741_rooted_global.tcl')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_predecessor_local_scope_rejected(self):
        result = self.exercise(adapter.TCL)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing global roots', result.stderr)


if __name__ == '__main__':
    unittest.main()
