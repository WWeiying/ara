"""Regression for the observed nested native selection and dirty reset popup."""
from pathlib import Path
import json
import subprocess
import unittest

import fma_datapath_native as native

HERE = Path(__file__).resolve().parent


class NativeTclTests(unittest.TestCase):
    def candidate(self):
        review = json.loads(native.one.REVIEW.read_bytes())
        formats = {f['format']: f for f in review['formats']}
        c = dict(instances=[dict(i, signals=formats[i['format']]['signals']) for i in review['instances']])
        return native.candidate_text(c['instances']), c

    def test_review_candidate_exact_108(self):
        text, c = self.candidate()
        self.assertEqual(len(native.parse_el(text, c)), 108)
        self.assertEqual(sum(s['width'] for i in c['instances'] for s in i['signals']), 8368)

    def test_candidate_extra_control_and_wrong_width_rejected(self):
        text, c = self.candidate()
        for bad in (text + 'Toggle busy_o "logic busy_o[0:0]"\n',
                    text.replace('product[47:0]', 'product[46:0]', 1)):
            with self.assertRaises(Exception):
                native.parse_el(bad, c)

    def run_tcl(self, body):
        source = (HERE / 'fma_datapath_native.tcl').read_text().split('if {[catch {fma_session} message]}')[0]
        result = subprocess.run(['tclsh'], input=source + '\n' + body, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertIn('TEST_PASS', result.stdout)

    def test_nested_singleton_unselect_and_readback(self):
        self.run_tcl(r'''
set calls {}
set answers [list [list [list {addend_after_shift[75:0]}]] [list [list {product[47:0]}]]]
proc gui_list_get_selected {args} {
    set answer [lindex $::answers 0]
    set ::answers [lrange $::answers 1 end]
    return $answer
}
proc gui_list_select {args} {lappend ::calls $args}
fma_select [list {product[47:0]} {product[47:0]} {product[47:0]}]
if {[lindex $calls 0 3] ne {addend_after_shift[75:0]}} {error "Nested unselect survived"}
if {[lindex $calls 1 3] ne [list {product[47:0]}]} {error "Wrong selection"}
puts TEST_PASS
''')

    def test_empty_and_multiple_normalization(self):
        self.run_tcl(r'''
if {[fma_flat {}] ne {}} {error "Empty differs"}
set multiple [list {a[7:0]} {b[3:0]}]
if {[fma_flat [list $multiple]] ne $multiple} {error "Multiple differs"}
puts TEST_PASS
''')

    def test_wrong_native_readback_rejected(self):
        self.run_tcl(r'''
proc gui_list_get_selected {args} {return [list [list {busy_o}]]}
proc gui_list_select {args} {}
if {![catch {fma_select [list {product[47:0]} {product[47:0]} {product[47:0]}]} reason]} {error "Wrong signal accepted"}
if {$reason ne "Selection readback differs"} {error $reason}
puts TEST_PASS
''')

    def test_cleanup_reset_recalculate_before_save(self):
        self.run_tcl(r'''
set calls {}
set env(DVE_COVERAGE_OUTPUT) /tmp/native-test
proc gui_exclusion {args} {lappend ::calls $args}
proc gui_process_events {args} {lappend ::calls [linsert $args 0 events]}
proc gui_exclusion_file {args} {lappend ::calls [linsert $args 0 save]}
fma_cleanup
if {[lindex $calls 0] ne {-reset}} {error "Not reset first"}
if {[lindex $calls 1] ne {-id CoverageTable.1 -recalculate}} {error "Not recalculate second"}
if {[lindex $calls 2 0] ne "events" || [lindex $calls 3 0] ne "save"} {error "Save before refresh"}
puts TEST_PASS
''')

    def test_cleanup_no_save_if_recalculate_failed(self):
        self.run_tcl(r'''
set saved 0
proc gui_exclusion {args} {if {[lsearch -exact $args -recalculate] >= 0} {error "recalculate failed"}}
proc gui_exclusion_file {args} {set ::saved 1}
if {![catch {fma_cleanup}] || $saved} {error "Unsafe cleanup save"}
puts TEST_PASS
''')


if __name__ == '__main__':
    unittest.main()
