import subprocess
import unittest
from pathlib import Path


class TclProbeTest(unittest.TestCase):
    def test_real_proc_source_and_path_lookup(self):
        hook = Path(__file__).with_name("diagnose_operand_hierarchy.tcl")
        script = """
set oph_library_only 1
proc load_probe {path} {global oph_library_only; source $path}
load_probe {%s}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {
        if {[llength $args] == 3} {return h0}
        if {[lindex $args end] eq "h0"} {return h1}
        return ""
    }
    if {[lsearch -exact $args -path] >= 0} {
        if {[lindex $args end] eq "h0"} {return ara_tb}
        return ara_tb.dut
    }
    return ""
}
proc gui_list_expand {args} {set ::expanded $args}
proc gui_process_events {} {incr ::events}
set events 0
if {[oph_find "" ara_tb.dut 0] ne "h1" || $events != 1} {error "Actual handle traversal failed"}
if {[oph_find "" ara_tb.absent 0] ne ""} {error "Missing scope accepted"}
if {![catch {oph_find "" ara_tb 33}]} {error "Depth guard missing"}
puts PASS
""" % hook
        result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
