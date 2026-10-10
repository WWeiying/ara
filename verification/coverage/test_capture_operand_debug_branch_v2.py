from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_operand_debug_branch_v2 as successor
from test_capture_operand_debug_branch import original_plan

b = successor.base


class SessionInitializationTests(unittest.TestCase):
    def test_real_session_loads_selection_arrays_globally(self):
        prelude = b.TCL.read_text().split("set failed [catch {dbg_session} message]", 1)[0]
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            test = output / "sample.vdb"
            (test / "snps/coverage/db/testdata/one").mkdir(parents=True)
            plan = b.branch_plan(original_plan(), "pilot")
            plan.update(design_vdb="unused.vdb", selected_test_vdb=str(test))
            (output / "selection.tcl").write_text(b.debug.selection(plan))
            (output / "live-ready").write_text("MOCK_IDENTITY_ONLY\n")
            script = prelude + '''
set env(DVE_COVERAGE_OUTPUT) {%s}
proc gui_open_cov {args} {
    global dbg_keys dbg_targets dbg_scopes
    if {![info exists dbg_keys(top.requester|branch)]} {error missing_global_keys}
    if {[lsort $dbg_targets(top.requester|branch)] ne "3,0 3,4"} {error wrong_targets}
    if {[llength $dbg_scopes] != 1 || [lindex $dbg_scopes 0] ne "top.requester"} {error wrong_scopes}
    set ::session_initialization_pass 1
    error STOP_BEFORE_GUI
}
catch {dbg_session} message
if {![info exists session_initialization_pass] || $message ne "STOP_BEFORE_GUI"} {error $message}
puts PASS
''' % d
            result = subprocess.run(["tclsh"], cwd="/tmp", input=script, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
