"""Read-only API boundary and mocked native inventory tests."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import lzc_selector_native_product_discover as discovery


MOCK = r'''
set lpd_test_only 1
source SCRIPT
set emitted {}
proc lpd_emit {values} {global emitted; lappend emitted $values}
set expressions [list {(a | b)} {((s == 1) ? l : r)}]
set selection {}
proc gui_cov_show_cond_ids {args} {}
proc gui_list_action {args} {global selection; set selection {}}
proc gui_covdetail_query {args} {return Condition}
proc gui_list_select {args} {
    global selection
    if {[lsearch -exact $args -unselect] >= 0} {set selection {}; return}
    set selection [lindex [lindex $args end] 0]
}
proc gui_list_get_selected {args} {
    global selection expressions
    set listname [lindex $args [expr {[lsearch -exact $args -list] + 1}]]
    if {[lsearch -exact $args -count] >= 0} {return [expr {$selection ne ""}]}
    if {$listname eq "cond"} {
        if {[lsearch -exact $args -all] >= 0} {
            if {$selection ne ""} {return [list [list $selection]]}
            return [list [list [lindex $expressions 0]] [list [lindex $expressions 1]]]
        }
        return [list [list $selection]]
    }
    if {$selection eq "(a | b)"} {return {00 01 10}}
    return {0 1}
}
'''


class DiscoveryTests(unittest.TestCase):
    def mock(self, tail):
        script = MOCK.replace('source SCRIPT', 'source {' + str(discovery.SCRIPT) + '}') + tail
        return subprocess.run(['tclsh'], input=script, text=True, capture_output=True, check=True)

    def test_script_readonly_and_selfcontained(self):
        text = discovery.SCRIPT.read_text()
        discovery.safe_script(text)
        self.assertNotIn('lzc_selector_native_capture', text)
        self.assertNotIn('apply_reviewed_waivers', text)

    def test_forbidden_api_rejected(self):
        for api in ('gui_exclusion -reset', 'gui_exclude_items', 'gui_cov_excl_review',
                    'exec tool', 'eval tool', 'gui_load_session', 'artifact.el'):
            with self.subTest(api=api), self.assertRaises(ValueError):
                discovery.safe_script(discovery.SCRIPT.read_text() + '\n' + api)

    def test_complete_true_false_vectors_from_native(self):
        result = self.mock('''
set count [lpd_conditions child $expressions]
if {$count != 5} {error "Wrong complete vector count"}
puts [list PASS $count $emitted]
''')
        self.assertIn('PASS 5', result.stdout)
        self.assertIn('{0 1}', result.stdout)
        self.assertIn('{00 01 10}', result.stdout)
        self.assertNotIn('error', result.stderr)

    def test_missing_or_extra_expression_rejected(self):
        result = self.mock('''
set failed [catch {lpd_conditions child [list {(a | b)}]} message]
if {!$failed || $message ne "Complete native expression inventory differs"} {error "Mismatch not rejected"}
puts PASS
''')
        self.assertIn('PASS', result.stdout)
        self.assertEqual(result.stderr, '')

    def test_wrong_output_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            discovery.prepare(discovery.product.OUT / 'missing', Path(directory) / 'discovery')


if __name__ == '__main__':
    unittest.main()
