import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import lzc_selector_native_prepare as native


class NativePrepareTests(unittest.TestCase):
    def test_compiled_parameter_binding(self):
        self.assertEqual(native.compiled_parameters(ET.fromstring(
            '<tgldef name="lzc ( parameter WIDTH=10,MODE=1,CNT_WIDTH=4,gen_lzc.NumLevels=4 ) "/>')),
            {'WIDTH': 10, 'MODE': 1, 'CNT_WIDTH': 4, 'gen_lzc.NumLevels': 4})
        for raw in ('WIDTH=10,WIDTH=23', 'WIDTH=10 + WIDTH=23', 'WIDTH'):
            with self.assertRaises(ValueError):
                native.compiled_parameters(ET.Element('tgldef', param=raw))

    def test_independent_root_selector_and_result_cross(self):
        for width in (10, 23):
            observed = set()
            for selector in (0, 1):
                for parity in (0, 1):
                    top, source = native.calibration_sv(width, selector, parity)
                    value = int(re.search(r"input_bits = \d+'h([0-9a-f]+)", source)[1], 16)
                    # Independent MODE1 permutation and root left reduction.
                    in_tmp = int(f'{value:0{width}b}'[::-1], 2)
                    middle = 1 << ((width - 1).bit_length() - 1)
                    self.assertEqual(bool(in_tmp & ((1 << middle) - 1)), bool(selector))
                    count = width - value.bit_length()
                    self.assertEqual(count % 2, parity)
                    self.assertIn(f'count !== {count}', source)
                    self.assertIn(f'sel_nodes[1] !== 1\'b{selector}', source)
                    self.assertTrue(top.startswith('lzc_selector_native_'))
                    observed.add((selector, parity))
            self.assertEqual(len(observed), 4)

    def test_prepare_is_only_fresh_files_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(native, 'OUT', root), patch.object(native, 'binding', return_value={
                    'protected': [], 'status': 'STATIC_BOUND_NATIVE_UNQUALIFIED'}), \
                    patch('subprocess.run', side_effect=AssertionError('unexpected launch')):
                output = root / 'lzc_selector_native_test'
                native.prepare(output)
                plan = json.loads((output / 'experiments.json').read_text())
                self.assertEqual(len(plan['experiments']), 8)
                self.assertFalse(plan['native_qualified'])
                self.assertFalse(plan['application_approval'])
                self.assertTrue(all(e['timeout_seconds'] == 120 for e in plan['experiments']))
                with self.assertRaises(ValueError):
                    native.prepare(output)

    def test_tcl_injection_rejected(self):
        for word in ('a}b', 'a{b', 'a\\b', 'a\nb', 'a\rb'):
            with self.assertRaises(ValueError):
                native.tcl_word(word)
        self.assertEqual(native.tcl_word('a[3].dut'), '{a[3].dut}')

    def test_foreign_processor_bind_rejected_before_reads(self):
        with self.assertRaises(ValueError):
            native.bind_case(native.OUT / 'processorPASS', native.OUT / 'capture')

    @unittest.skipUnless(shutil.which('tclsh'), 'host Tcl required')
    def test_tcl_roundtrip_protected_audit_and_selection_failures(self):
        helper = Path(native.__file__).with_name('lzc_selector_native_capture.tcl')
        with tempfile.TemporaryDirectory() as directory:
            script = r'''
set lsn_library_only 1
source HELPER
set lsn_output OUTPUT
set lsn_scope lzc_selector_native_mock.dut
set lsn_rows {{branch 1 0 expr} {branch 1 1 expr} {cond 2 0 expr2} {cond 2 1 expr2}}
set state -1
set current -1
array set saved {}
proc lsn_branches {} {}
proc lsn_row {row} {
    global lsn_rows current
    set current [lsearch -exact $lsn_rows $row]
    return [expr {[lindex $row 0] eq "branch" ? "branch" : "vector"}]
}
proc gui_exclusion {args} {
    global state current
    if {[lindex $args 0] eq "-reset"} {set state -1; return}
    if {[lsearch -exact $args -recalculate] >= 0} {return}
    return [expr {$state == $current}]
}
proc gui_exclude_items {args} {global state current; set state $current}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    global saved state
    set path [lindex [lindex $args end] 0]
    if {[lindex $args 0] eq "-load"} {set state $saved($path); return}
    set saved($path) $state
    set f [open $path w]
    if {$state >= 0} {puts $f "singleton $state"}
    close $f
}
lsn_audit before -1
set listname [lsn_row [lindex $lsn_rows 2]]
gui_exclude_items -list $listname
lsn_audit selected 2
lsn_save first.el 0
gui_exclusion -reset
lsn_audit reset -1
lsn_save reset.el 1
gui_exclusion_file -load -file [list [file join $lsn_output first.el]]
lsn_audit reloaded 2
lsn_save second.el 0
lsn_same_file first.el second.el
set file [open [file join $lsn_output second.el] w]
puts $file changed
close $file
if {![catch {lsn_same_file first.el second.el} message]} {error "native signature drift accepted"}
set file [open [file join $lsn_output second.el] w]
puts $file "singleton 2"
close $file
set state 3
if {![catch {lsn_audit wrong 2} message]} {error "collateral exclusion accepted"}
gui_exclusion -reset
lsn_audit final -1
lsn_save final.el 1
set stuck 1
proc gui_list_get_selected {args} {
    if {[lindex $args end] eq "-count"} {return 1}
    return wrong
}
proc gui_list_select {args} {}
if {![catch {lsn_select vector 1} message]} {error "stuck deselection accepted"}
rename gui_list_get_selected {}
proc gui_list_get_selected {args} {
    if {[lindex $args end] eq "-count"} {return 0}
    return wrong
}
if {![catch {lsn_select vector 1} message]} {error "wrong singleton accepted"}
puts HOST_ONLY_TEST_PASS
'''.replace('HELPER', native.tcl_word(helper)).replace('OUTPUT', native.tcl_word(directory))
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertIn('HOST_ONLY_TEST_PASS', result.stdout)
            self.assertEqual((Path(directory) / 'first.el').read_bytes(),
                             (Path(directory) / 'second.el').read_bytes())
            self.assertEqual((Path(directory) / 'final.el').read_bytes(), b'')
            self.assertEqual(len((Path(directory) / 'final.tsv').read_text().splitlines()), 5)


if __name__ == '__main__':
    unittest.main()
