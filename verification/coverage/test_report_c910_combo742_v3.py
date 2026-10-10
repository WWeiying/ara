import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import report_c910_combo742_v3 as v3

report = v3.prior.prior
FIXTURE = report.life.OUT / 'qualified-native-combo-full742-agent-20261007-02'
DWC = report.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-03'


def atom(value):
    value = str(value)
    if any(c in value for c in '{}\\\r\n'):
        raise ValueError('Unsafe test Tcl fixture')
    return '{' + value + '}'


class WholeHookTests(unittest.TestCase):
    def execute(self, fixed):
        c = json.loads((FIXTURE / 'config.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name in ('selection.tcl', 'combined.el'):
                (out / name).write_bytes((FIXTURE / name).read_bytes())
            (out / 'live-ready').touch()
            hook = report.TCL if fixed else report.HERE / 'report_c910_combo742.tcl'
            script = 'source %s\nset ::env(DVE_COVERAGE_OUTPUT) %s\n' % (atom(hook), atom(out))
            for group in c['toggle_groups']:
                rows = ' '.join('[list ' + ' '.join(atom(x) for x in row) + ']'
                                for row in group['reference'])
                script += 'set %s [list %s]\n' % (atom('::trees(' + group['scope'] + ')'), rows)
            for index, group in enumerate(sorted({t['scope'] for t in c['dwc_config']['toggles']})):
                with (DWC / ('toggle-before-%d.tsv' % index)).open() as stream:
                    rows = list(csv.reader(stream, delimiter='\t'))
                script += 'set %s [list %s]\n' % (atom('::trees(' + group + ')'), ' '.join(
                    '[list ' + ' '.join(atom(x) for x in row[1:]) + ']' for row in rows))
            script += r'''
set ::opens 0
set ::active 0
set ::selected {}
set ::scope {}
set ::metric {}
set ::calls {}
set ::original_fx [info body fx_audit]
proc gui_open_cov {args} {
    incr ::opens
    if {$::opens != 1} {error SECOND_GUI_OPEN_FORBIDDEN}
}
proc gui_exit {args} {error STANDALONE_GUI_EXIT_FORBIDDEN}
proc p740_root {} {}
proc gui_process_events {args} {}
proc gui_list_expand {args} {}
proc gui_list_action {args} {
    set ::scope [lindex $args end]
    set ::metric [lindex $args end-1]
    set ::selected {}
}
proc gui_covdetail_query {args} {return $::metric}
proc fx_context {group} {set ::context $group; set ::metric FSM; set ::selected {}}
proc fs_select {name} {set ::selected $name}
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -count] >= 0} {return [expr {$::selected ne ""}]}
    return [list $::selected]
}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {}; return}
    set ::selected [lindex [lindex $args end] 0]
}
proc gui_list_get {args} {
    set n [llength $::trees($::scope)]
    set index [lsearch -exact $args -firstChild]
    if {$index >= 0} {return [expr {$index == [llength $args]-1 && $n > 0 ? 1 : 0}]}
    set handle [lindex $args end]
    if {[lsearch -exact $args -nextSibling] >= 0} {return [expr {$handle < $n ? $handle+1 : 0}]}
    set row [lindex $::trees($::scope) [expr {$handle-1}]]
    if {[lsearch -exact $args -path] >= 0} {return [lindex $row 0]}
    if {[lsearch -exact $args -meta] >= 0} {return [lindex $row 1]}
    if {[lsearch -exact $args -text] >= 0} {return [lindex $row 2]}
    error UNKNOWN_NATIVE_GET
}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset] >= 0} {set ::active 0; lappend ::calls reset; return}
    if {[lsearch -exact $args -recalculate] >= 0} {lappend ::calls recalculate; return}
    if {[lsearch -exact $args -excluded] < 0 || [lsearch -exact $args -selected] < 0} {error UNKNOWN_EXCLUSION_QUERY}
    if {!$::active} {return 0}
    if {$::metric eq "FSM"} {return [expr {[lsearch -exact [lindex $::context 5] $::selected] >= 0}]}
    foreach group $::dw_toggles {
        if {[lindex $group 0] eq $::scope} {
            return [expr {[lsearch -exact [lindex $group 1] $::selected] >= 0}]
        }
    }
    error UNBOUND_SELECTED_TOGGLE
}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -load] >= 0} {
        set stream [open $path r]; set ::loaded [read $stream]; close $stream
        set ::active 1; lappend ::calls load; return
    }
    if {[lsearch -exact $args -save] < 0} {error UNKNOWN_EXCLUSION_FILE}
    set stream [open $path w]
    if {$::active} {puts -nonewline $stream $::loaded}
    close $stream
    lappend ::calls save_[file tail $path]
}
proc p740_summary {stage} {
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) mock_summary_${stage}.txt] w]
    puts $stream $::active
    close $stream
    lappend ::calls summary_$stage
}
# Simulate the exporter's single database open, then invoke the real hook.
gui_open_cov -hier FROZEN_DESIGN -test MOCK742
set failed [catch {apply_reviewed_waivers CoverageTable.1} message]
puts "HOST_RESULT failed=$failed opens=$::opens message=$message"
puts "FX_PRESERVED [expr {[info body fx_audit] eq $::original_fx}]"
puts "DW_SESSION_PRESENT [expr {[llength [info procs dw_session]] > 0}]"
puts "CALLS $::calls"
'''
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=30,
                                    cwd='/tmp')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            if not fixed:
                self.assertIn('SECOND_GUI_OPEN_FORBIDDEN', result.stdout)
                self.assertIn('opens=2', result.stdout)
                return
            self.assertIn('HOST_RESULT failed=0 opens=1', result.stdout)
            self.assertIn('FX_PRESERVED 1', result.stdout)
            self.assertIn('DW_SESSION_PRESENT 0', result.stdout)
            self.assertFalse((out / 'error.txt').exists(), result.stdout)
            for name in ('applied.el', 'reloaded.el'):
                self.assertEqual(report.records((out / name).read_text(), c), c['expected_union'])
            for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
                self.assertEqual((out / name).read_bytes(), b'')
            with (out / 'exact-audit.tsv').open() as stream:
                report.base.native.audit_points(list(csv.reader(stream, delimiter='\t')), c['plan'])
            for index, group in enumerate(c['toggle_groups']):
                for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
                    self.assertEqual(report.native_tree(out / ('combo_%s_%d.tsv' % (stage, index))),
                                     [tuple(r) for r in group['reference']])
            with (out / 'dwc-audit.tsv').open() as stream:
                rows = list(csv.reader(stream, delimiter='\t'))
            self.assertEqual(len(rows), 355)
            for row in rows:
                self.assertIn(row[5], ('0', '1'))
                if row[6] != 'EL_AUTHORITY':
                    self.assertEqual(row[5], row[6])
            self.assertEqual([(out / ('mock_summary_' + s + '.txt')).read_text().strip()
                              for s in ('raw', 'applied', 'reset', 'reloaded', 'final')],
                             ['0', '1', '0', '1', '0'])
            self.assertIn('summary_final reset recalculate save_cleanup-empty.el', result.stdout)

    def test_old_real_nested_source_reproduces_second_open(self):
        self.execute(False)

    def test_real_full_combined_hook_procedure_import_and_all_parsers(self):
        self.execute(True)

    def test_frozen_dependencies(self):
        v3.life.check(v3.PINS)


if __name__ == '__main__':
    unittest.main()
