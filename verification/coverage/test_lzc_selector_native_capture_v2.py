from pathlib import Path
import subprocess
import unittest


class SelectionTests(unittest.TestCase):
    def test_nested_exact_selection_and_wrong_identity(self):
        script = r'''
set lsn_v2_test_only 1
source HELPER
set returned {{{(left == 1'b1)}}}
set count 1
proc gui_list_get_selected {args} {
    global returned count
    if {[lindex $args end] eq "-count"} {return $count}
    return $returned
}
proc gui_list_select {args} {
    global count
    if {[lsearch -exact $args -unselect] >= 0} {set count 0} else {set count 1}
}
lsn_select cond {(left == 1'b1)}
set returned wrong
if {![catch {lsn_select cond {(left == 1'b1)}}]} {error "wrong identity accepted"}
puts HOST_SELECTION_PASS
'''.replace('HELPER', '{' + str(Path(__file__).with_name('lzc_selector_native_capture_v2.tcl')) + '}')
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertIn('HOST_SELECTION_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
