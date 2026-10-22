from pathlib import Path
import subprocess
import unittest


class UpdateErrorTest(unittest.TestCase):
    def test_update_error_is_recorded_and_read_is_not_success_claim(self):
        hook = Path(__file__).with_name("probe_operand_root_update_v2.tcl")
        script = """
set oph7_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) /not-used
proc gui_exclusion {args} {error 0}
proc gui_process_events {args} {set ::events $args}
proc oph6_root_row {scope stage} {set ::read [list $scope $stage]}
rename open real_open
proc open {args} {return fake}
rename puts real_puts
proc puts {args} {lappend ::writes $args}
rename close real_close
proc close {args} {}
set writes {}
oph7_update i_system
if {$read ne {i_system update} || $events ne {-mstime 100}} {error "Post-error read missing"}
set found 0
foreach row $writes {if {[string first "i_system\t1\t0\t" [lindex $row end]] == 0} {set found 1}}
if {!$found} {error "API error was not preserved"}
rename puts muted_puts
rename real_puts puts
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
