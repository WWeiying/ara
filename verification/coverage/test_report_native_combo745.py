import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import report_native_combo745 as report


class NativeUnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = json.loads((report.REFERENCE / 'config.json').read_bytes())
        c['fp16_config'] = json.loads((report.FP16 / 'config.json').read_bytes())
        c['queue_config'] = json.loads((report.QUEUE / 'config.json').read_bytes())
        cls.config = c
        cls.text = ''.join((p / name).read_text() for p, name in
            [(report.REFERENCE, 'applied.el'), (report.FP16, 'first.el'), (report.QUEUE, 'first.el')])

    def test_actual_native_union_all_three_parsers(self):
        parsed = report.records(self.text, self.config)
        self.assertEqual(len(parsed['original']['c910']), 1264)
        self.assertEqual(len(parsed['fp16']), 1264)
        self.assertEqual(len(parsed['queue']), 312)

    def test_unknown_scope_rejected(self):
        with self.assertRaises(ValueError):
            report.records(self.text.replace('INSTANCE: ', 'INSTANCE: injected.', 1), self.config)

    def test_protected_usage_rejected(self):
        text = (report.QUEUE / 'first.el').read_text().replace('Toggle ', 'Toggle ', 1)
        text += 'Toggle 0to1 usage_d [0]\n'
        with self.assertRaises(ValueError):
            report.QN['parse_el'](text, self.config['queue_config'])

    def test_duplicate_direction_rejected(self):
        with self.assertRaises(ValueError):
            report.records(self.text + (report.QUEUE / 'first.el').read_text(), self.config)

    def test_receipt_exact_existing_prefix(self):
        q = json.loads((report.FP16 / 'capture-result.json').read_bytes())
        r = json.loads((report.FP16 / 'postterminal-receipt.json').read_bytes())
        pins = report.receipt_pins(q, r)
        self.assertEqual(pins[str(report.FP16 / 'worker.log')], r['pins'][str(report.FP16 / 'worker.log')])
        r['pin_ledger']['overrides']['/injected'] = '0' * 64
        with self.assertRaises(ValueError):
            report.receipt_pins(q, r)

    def test_actual_hierarchy_collapsed_generate_roots(self):
        rows = report.dict_rows(report.REFERENCE / 'summary.csv.partial')
        roots = report.hierarchy(rows)
        self.assertTrue(any('i_qbs_engine' in r['scope'] for r in roots))
        self.assertTrue(any('operand_queue' in r['scope'] for r in roots))
        self.assertFalse(any(r['scope'].endswith('gen_lanes[0]') for r in roots))

    def test_complete_subprocess_namespace_and_hook_override(self):
        def fake(*args, **kwargs):
            self.assertEqual(kwargs['env']['DVE_REVIEWED_WAIVERS'], str(report.TCL))
            self.assertEqual(kwargs['stderr'], subprocess.STDOUT)
            return 'PROCESS'
        def lifecycle(out, seal):
            return subprocess.Popen(['native'], env={'DVE_REVIEWED_WAIVERS': 'old'}, stderr=subprocess.STDOUT)
        with patch.object(report.old.base, 'run', lifecycle), patch.object(report.subprocess, 'Popen', fake):
            report.run(Path('/unused'), 'seal')


class HookTests(unittest.TestCase):
    def test_actual_proc_import_and_full_hook_five_stages(self):
        # Load real nested procedures, then mock only native GUI APIs and independently
        # tested original combo audits. The real queue traversal and root rows run.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'live-ready').touch()
            (out / 'combined.el').write_text('NATIVE_UNION\n')
            (out / 'selection.tcl').write_text(
                'set fx_groups {}\nset combo_groups {}\nset combo_has_dwc 0\n'
                'set qc_instances [list [list ara_tb.queue [list data]]]\n'
                'set report745_roots [list [list ara_tb.queue queue]]\n')
            script = 'source {%s}\nset ::env(DVE_COVERAGE_OUTPUT) {%s}\n' % (report.TCL, out)
            # csv_row is an actual dependency of both rooted exports, not a fake stub.
            exporter = (report.HERE / 'export_dve_coverage.tcl').read_text()
            script += exporter[:exporter.index('proc export_rows')]
            script += r'''
set ::opens 0
set ::active 0
set ::selected {}
set ::root ara_tb
set ::metric Toggle
proc gui_open_cov {args} {incr ::opens; if {$::opens > 1} {error SECOND_OPEN}}
proc gui_exit {args} {error STANDALONE_EXIT}
proc fx_audit {args} {}
proc combo_inventory {args} {}
proc gui_process_events {args} {}
proc gui_list_expand {args} {}
proc gui_covtable_show {args} {}
proc gui_cov_show_value {args} {}
proc gui_covtable_setroot {args} {set ::root [lindex $args end]}
proc gui_list_action {args} {set ::metric [lindex $args end-1]}
proc gui_covdetail_query {args} {return $::metric}
proc gui_list_get_property {args} {
    set i [lindex $args end]
    if {$i > 10} {error END}
    return [lindex {Score Line Toggle FSM Condition Branch} [expr {$i-5}]]
}
proc gui_list_get_selected {args} {return [list $::selected]}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::selected {}; return}
    set ::selected [lindex $args end]
}
proc gui_list_get {args} {
    set detail [expr {[lindex $args 1] eq "CovDetail.1"}]
    if {[lsearch -exact $args -firstChild] >= 0} {
        return [expr {[lindex $args end] eq "-firstChild" ? 1 : 0}]
    }
    if {[lsearch -exact $args -nextSibling] >= 0} {return 0}
    if {[lsearch -exact $args -path] >= 0} {
        if {$detail} {return data}
        return [lindex [split $::root .] end]
    }
    if {[lsearch -exact $args -meta] >= 0} {return reg}
    set ix [lsearch -exact $args -text]
    set col [lindex $args [expr {$ix+1}]]
    if {$detail} {
        if {$col == 0} {return data}
        return 0
    }
    if {$col == 0} {return [lindex [split $::root .] end]}
    return [expr {50+$::active}]
}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset] >= 0} {set ::active 0}
}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -load] >= 0} {
        set s [open $path r]; set ::loaded [read $s]; close $s
        set ::active 1; return
    }
    set s [open $path w]
    if {$::active} {puts -nonewline $s $::loaded}
    close $s
}
gui_open_cov
set failed [catch {apply_reviewed_waivers CoverageTable.1} message]
puts "RESULT $failed $::opens $message"
puts "NO_STANDALONE [expr {[llength [info procs qc_session]] == 0 && [llength [info procs dw_session]] == 0}]"
'''
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.stderr, '')
            self.assertIn('RESULT 0 1', result.stdout)
            self.assertIn('NO_STANDALONE 1', result.stdout)
            for stage in report.STAGES:
                rows = report.dict_rows(out / ('modules_' + stage + '.csv'))
                self.assertEqual(rows[0]['Scope'], 'ara_tb.queue')
                self.assertEqual(rows[0]['Toggle'], '51' if stage in ('applied', 'reloaded') else '50')
            for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
                self.assertIn('data', (out / ('native_' + stage + '_0.tsv')).read_text())
            for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
                self.assertEqual((out / name).read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()
