from pathlib import Path
import subprocess
import unittest


class EventReadTest(unittest.TestCase):
    def test_fixed_reads_do_not_dispatch_events_and_reject_reused_handle(self):
        hook = Path(__file__).with_name("probe_operand_root_events.tcl")
        script = """
set oph5_library_only 1
source {%s}
set oph5_scopes {ara_tb}
set oph5_handles(ara_tb) handle1
proc gui_list_get {args} {return ara_tb}
proc gui_process_events {args} {error "Unexpected event dispatch"}
proc gui_list_expand {args} {error "Unexpected expansion"}
proc gui_cov_show_value {args} {error "Unexpected mode change"}
proc oph_write {stage scope handle} {set ::saved [list $stage $scope $handle]}
oph5_fixed_read immediate_a
if {$saved ne {immediate_a ara_tb handle1}} {error "Read differs"}
rename gui_list_get good_get
proc gui_list_get {args} {return other}
if {![catch {oph5_fixed_read immediate_b}]} {error "Reused handle accepted"}
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
