"""Product hierarchy expansion order and read-only successor boundaries."""
import subprocess
import unittest

import lzc_selector_native_product_discover_v3 as discovery


class ExpansionTests(unittest.TestCase):
    def test_successor_and_loaded_library_readonly(self):
        discovery.safe_script(discovery.SCRIPT.read_text())
        for extra in ('gui_exclusion -reset', 'gui_exclude_items', 'eval dangerous', 'source arbitrary'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                discovery.safe_script(discovery.SCRIPT.read_text() + '\n' + extra)

    def test_actual_tcl_expands_before_first_child(self):
        script = 'set lpd_v3_test_only 1\nsource {' + str(discovery.SCRIPT) + '}\n' + r'''
set expanded 0
proc gui_open_cov {args} {}
proc gui_list_expand {args} {global expanded; set expanded 1}
proc lpd_branch {scope} {global expanded; if {!$expanded} {error "Not expanded"}; return 24}
proc lpd_conditions {scope expected} {return 60}
proc lpd_emit {args} {}
rename source original_source
proc source {path} {
    global lpd_design lpd_testdirs lpd_tests lpd_children
    set lpd_design mock_design
    set lpd_testdirs mock_dirs
    set lpd_tests {}
    for {set i 0} {$i < 707} {incr i} {lappend lpd_tests "test$i"}
    set lpd_children {}
    for {set i 0} {$i < 36} {incr i} {lappend lpd_children [list "child$i" 3250293308 WIDTH=10 expressions]}
}
rename open original_open
rename close original_close
proc open {args} {return mock_stream}
proc close {args} {}
set env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION) mock_selection
set env(LZC_SELECTOR_NATIVE_PRODUCT_OUTPUT) mock_output
if {[catch {lpd_session} message]} {puts stderr $message; exit 1}
puts TEST_PASS
'''
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, check=True)
        self.assertIn('TEST_PASS', result.stdout)
        self.assertEqual(result.stdout.count('LZC_PRODUCT_READONLY_CHILD_COMPLETE'), 36)
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
