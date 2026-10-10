"""Actual source/session/eval scoping, without any EDA process."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import fma_expanded_native_02 as successor


class SessionScopeTests(unittest.TestCase):
    def simulate(self, script, selection):
        text = script.read_text()
        marker = 'if {[catch {fma_session} message]}'
        self.assertEqual(text.count(marker), 1)
        definitions, entry = text.split(marker)
        mock = r'''
set calls {}
set excluded 0
set stages {}
proc gui_open_cov {args} {lappend ::calls [linsert $args 0 open]}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_exclusion {args} {lappend ::calls [linsert $args 0 exclusion]}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {lappend ::calls [linsert $args 0 file]}
proc gui_exclude_items {args} {incr ::excluded}
proc gui_exit {args} {}
proc fma_bind {stage instance} {
    if {[llength $instance] != 3 || [llength [lindex $instance 1]] != 51} {error "Scope shrunk"}
    set rows {}
    foreach name [lindex $instance 1] {lappend rows [list $name $name $name]}
    return $rows
}
proc fma_select {row} {}
proc exec {args} {
    foreach variable {fma_scope fma_design fma_vdb fma_test fma_python fma_helper fma_instances fma_seal} {
        if {![info exists ::$variable] || [set ::$variable] eq ""} {error "Missing global $variable"}
    }
    if {[llength $::fma_instances] != 12} {error "Not twelve scopes"}
    if {[lindex $args 0] ne $::fma_python || [lindex $args 2] ne $::fma_helper} {error "Wrong helper command"}
    if {$::fma_helper ne $::expected_helper} {error "Wrong successor helper"}
    if {[lrange $args 3 3] ne "stage" || [lindex $args 4] ne "--output" ||
        [lindex $args 5] ne $::env(DVE_COVERAGE_OUTPUT) || [lindex $args 7] ne "mock-seal"} {error "Wrong arguments"}
    lappend ::stages [lindex $args 9]
    return MOCK_STAGE_PASS
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'selection.tcl').write_text(selection)
            setup = ('set env(DVE_COVERAGE_OUTPUT) {' + str(out) + '}\n'
                     'set env(FMA_EXPANDED_CONFIG_SEAL) mock-seal\n'
                     'set expected_helper {' + str(Path(successor.__file__).resolve()) + '}\n')
            # stdin eval reproduces DVE's empty top-level info script context.
            program = setup + 'eval {' + definitions + '}\n' + mock + '\neval {' + marker + entry + '}\n'
            program += '\nputs [list STATE $excluded $stages INFO_SCRIPT [info script]]\nputs [list CALLS $calls]\n'
            result = subprocess.run(['tclsh'], input=program, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_original_defect_reproduced_with_actual_selection(self):
        result = self.simulate(successor.HERE / 'fma_expanded_native.tcl',
                               (successor.OLD / 'selection.tcl').read_text())
        self.assertIn('FMA_EXPANDED_NATIVE_CAPTURE_FAILED can\'t read "::fma_python"', result)
        self.assertIn('STATE 0 {} INFO_SCRIPT {}', result)
        self.assertNotIn('FMA_EXPANDED_NATIVE_CAPTURE_DONE', result)

    def test_successor_eval_source_all_globals_and_five_stages(self):
        result = self.simulate(successor.HERE / 'fma_expanded_native_02.tcl', successor.selection_text())
        self.assertIn('FMA_EXPANDED_NATIVE_CAPTURE_DONE', result)
        self.assertNotIn('FMA_EXPANDED_NATIVE_CAPTURE_FAILED', result)
        self.assertIn('STATE 612 {initial apply reset reload final} INFO_SCRIPT {}', result)
        self.assertEqual(result.count('MOCK_STAGE_PASS'), 5)
        for filename in ('initial-empty.el', 'first.el', 'reset-empty.el', 'second.el', 'final-empty.el'):
            self.assertIn(filename, result)
        self.assertNotIn('cleanup-empty.el', result)

    def test_tcl_only_global_binding_changed(self):
        old = (successor.HERE / 'fma_expanded_native.tcl').read_text().splitlines()
        new = (successor.HERE / 'fma_expanded_native_02.tcl').read_text().splitlines()
        self.assertEqual(len(old), len(new))
        changes = [(a, b) for a, b in zip(old[1:], new[1:]) if a != b]
        self.assertEqual(changes, [('    global env fma_instances fma_design fma_vdb fma_test',
                                   '    global env fma_instances fma_scope fma_design fma_vdb fma_test fma_python fma_helper')])

    def test_selection_only_helper_changed(self):
        old = (successor.OLD / 'selection.tcl').read_text().splitlines()
        new = successor.selection_text().splitlines()
        self.assertEqual(old[:-1], new[:-1])
        self.assertEqual(new[-1], 'set fma_helper {' + str(Path(successor.__file__).resolve()) + '}')


if __name__ == '__main__':
    unittest.main()
