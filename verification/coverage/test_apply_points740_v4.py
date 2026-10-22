"""Offline eleven-root/EL/diagnostic contracts; no GUI or simulation launch."""
import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import apply_points740_v4 as p

EL = (b'CHECKSUM: "10 20"\nINSTANCE: top.unit\nANNOTATION: "old"\n'
      b'Branch 3 "40" "if (x)" (1) "else"\n')
RAW_HEADER = ['Name', 'Depth', *p.METRICS]


def raw_file(path):
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(RAW_HEADER)
        for scope in p.ROOTS:
            writer.writerow([scope, 0] + ['50.00%'] * 6)
        writer.writerow(['uvm_custom_install_verdi_recording', 0] + ['3.00%'] * 6)


def rooted_file(path, names, stage):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=p.ROOT_HEADER); writer.writeheader()
        for scope in p.ROOTS:
            row = dict(Stage=stage, Scope=scope, Token=scope, Handle='123', GUIPath=names[scope], Name=names[scope])
            row.update({m: '50.00%' for m in p.METRICS})
            if stage in ('applied', 'reloaded'):
                row.update(Score='51.00%', Branch='55.00%', Condition='52.00%')
            writer.writerow(row)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'out'; self.out.mkdir()
        self.raw = Path(self.temp.name) / 'raw'; self.raw.mkdir()
        raw_file(self.raw / 'summary.csv'); raw_file(self.out / 'raw.csv')
        self.names = p.root_names(p.table(self.raw / 'summary.csv'))
        self.c = dict(records=1, inputs=['design', 'test'], selected_tests=['native'], report=str(self.raw),
                      formal_scopes=list(p.ROOTS), root_names=self.names, pins={}, tool_identity=dict(executable='/sealed/dve.exe'))
        live = dict(executable_verified=True, executable='/sealed/dve.exe', pid=10)
        (self.out / 'live-identity.json').write_text(json.dumps(live))
        (self.out / 'terminal.json').write_text(json.dumps(dict(returncode=0, live_identity=live)))
        (self.out / 'DVEfiles').mkdir()
        (self.out / 'run.log').write_text('')
        (self.out / 'DVEfiles/dve_gui.log').write_text('DVE_SELECTED_TESTS: native\nPOINT740_APPLIED_RELOADED_RESET_DONE\nDVE_COVERAGE_EXPORT_DONE\n')
        (self.out / 'inputs.txt').write_text('design\ntest\n'); (self.out / 'selected_tests.txt').write_text('native\n')
        for name in ('points.el', 'applied.el', 'reloaded.el'): (self.out / name).write_bytes(EL)
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'): (self.out / name).write_bytes(b'')
        for stage in ('raw', 'applied', 'reloaded', 'reset'): rooted_file(self.out / ('rooted_' + stage + '.csv'), self.names, stage)
        rooted_file(self.out / 'summary_waived.csv', self.names, 'applied')
        mock = patch.object(p.tools, 'revalidate'); mock.start(); self.addCleanup(mock.stop)

    def inspect(self): return p.inspect(self.c, self.out)

    def mutate(self, name, row_index, field, value):
        path = self.out / name
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream); header = reader.fieldnames; rows = list(reader)
        rows[row_index][field] = value
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=header); writer.writeheader(); writer.writerows(rows)

    def test_good_exact_eleven_not_fullhier_claim(self):
        result = self.inspect()
        self.assertEqual(result['formal_scope_count'], 11)
        self.assertEqual(result['protected_row_metric_checks'], 66)
        self.assertFalse(result['full_hierarchy_fresh'])
        self.assertFalse(result['full_after_cached_is_formal'])
        self.assertEqual(result['rooted_metrics']['applied'][p.SYSTEM]['Branch'], '55.00%')

    def test_extra_UVM_rawroot_retained_and_required(self):
        path = self.out / 'raw.csv'; lines = path.read_text().splitlines(); path.write_text('\n'.join(lines[:-1]) + '\n')
        with self.assertRaisesRegex(ValueError, 'Original full raw740'): self.inspect()

    def test_raw_and_reset_rooted_must_match_original(self):
        for stage in ('raw', 'reset'):
            path = self.out / ('rooted_' + stage + '.csv'); old = path.read_text()
            self.mutate(path.name, 0, 'Branch', '49.00%')
            with self.assertRaises(ValueError): self.inspect()
            path.write_text(old)

    def test_applied_reloaded_mismatch(self):
        self.mutate('rooted_reloaded.csv', 0, 'Branch', '54.00%')
        with self.assertRaisesRegex(ValueError, 'Reload rooted'): self.inspect()

    def test_all_protected_metrics_even_both_stages_match(self):
        for metric in p.PROTECTED_METRICS:
            for stage in ('applied', 'reloaded'): self.mutate('rooted_' + stage + '.csv', 0, metric, '51.00%')
            with self.assertRaisesRegex(ValueError, 'Protected rooted metric'): self.inspect()
            for stage in ('applied', 'reloaded'): self.mutate('rooted_' + stage + '.csv', 0, metric, '50.00%')

    def test_root_token_path_name_handle_stage_reject(self):
        path = self.out / 'rooted_applied.csv'; original = path.read_text()
        for field, value in (('Token', 'wrong'), ('Scope', 'wrong'), ('GUIPath', 'wrong'), ('Name', 'wrong'),
                             ('Handle', '0'), ('Stage', 'raw')):
            self.mutate(path.name, 0, field, value)
            with self.assertRaises(ValueError): self.inspect()
            path.write_text(original)

    def test_missing_duplicate_root_and_wrong_formal_summary(self):
        path = self.out / 'rooted_applied.csv'; original = path.read_text()
        self.mutate(path.name, 1, 'Scope', p.ROOTS[0])
        with self.assertRaises(ValueError): self.inspect()
        path.write_text(original)
        self.mutate('summary_waived.csv', 0, 'Branch', '54.00%')
        with self.assertRaisesRegex(ValueError, 'Formal waived summary'): self.inspect()

    def test_exact_el_extra_checksum_duplicate_rejected(self):
        path = self.out / 'applied.el'
        for raw in (EL + EL, EL.replace(b'"40"', b'"41"'), b'CHECKSUM: "10 20"\nINSTANCE: top.unit\n'):
            path.write_bytes(raw)
            with self.assertRaises(ValueError): self.inspect()

    def test_each_global_empty_and_actualmembership(self):
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
            path = self.out / name; path.write_bytes(EL)
            with self.assertRaises(ValueError): self.inspect()
            path.write_bytes(b'')
        (self.out / 'selected_tests.txt').write_text('wrong\n')
        with self.assertRaises(ValueError): self.inspect()

    def test_only_exact_qt_allowed_not_DVEENVDIRNFND(self):
        (self.out / 'DVEfiles/dve_qtwarnings.log').write_text(p.KNOWN_QT + '\n')
        self.assertEqual(len(self.inspect()['diagnostics']['observed_allowed_lines']), 1)
        (self.out / 'run.log').write_text('\nWarning-[DVEENVDIRNFND] DVE warning\n  Environment variable DVE is set. Please unset it.\n\n')
        with self.assertRaises(ValueError): self.inspect()

    def test_nonzero_terminal_pin_drift_and_missingmarker(self):
        path = self.out / 'terminal.json'; original = path.read_text(); d = json.loads(original); d['returncode'] = 124
        path.write_text(json.dumps(d))
        with self.assertRaises(ValueError): self.inspect()
        path.write_text(original)
        self.c['pins'] = {str(self.out / 'points.el'): 'a'*64}
        with self.assertRaises(ValueError): self.inspect()
        self.c['pins'] = {}
        path = self.out / 'DVEfiles/dve_gui.log'; path.write_text(path.read_text().replace('DVE_COVERAGE_EXPORT_DONE', ''))
        with self.assertRaises(ValueError): self.inspect()


class TclTests(unittest.TestCase):
    def test_complete_actual_host_body_all44_rooted_rows(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); names = {scope: scope.rsplit('.', 1)[-1] for scope in p.ROOTS}
            (root / 'root-selection.tcl').write_text(p.root_selection(names))
            (root / 'summary.csv.partial').write_text('original full raw with UVM\n')
            (root / 'points.el').write_bytes(EL)
            t = tkinter.Tcl(); t.setvar('env(DVE_COVERAGE_OUTPUT)', d)
            t.eval('''
                set native {}; set selected {}; set current ara_tb; set visits 0; set ready 0
                proc gui_covtable_show {args} {}
                proc gui_covtable_setroot {args} {set ::current [lindex $args end]; set ::ready 0}
                proc gui_list_expand {args} {}
                proc gui_cov_show_value {args} {}
                proc gui_process_events {args} {set ::ready 1}
                proc gui_list_get_selected {args} {return [list $::selected]}
                proc gui_list_select {args} {
                    if {[lsearch -exact $args -select] >= 0} {set ::selected [lindex $args end]} else {set ::selected {}}
                }
                proc gui_list_get_property {args} {
                    set labels {Score Line Toggle FSM Condition Branch}
                    set n [expr {[lindex $args end] - 5}]
                    if {$n >= 6} {error end}; return [lindex $labels $n]
                }
                proc gui_list_get {args} {
                    if {!$::ready} {error "Root not processed before read"}
                    if {[lsearch -exact $args -firstChild] >= 0} {return 123}
                    if {[lsearch -exact $args -nextSibling] >= 0} {return 0}
                    if {[lsearch -exact $args -path] >= 0} {return [lindex [split $::current .] end]}
                    set n [lindex $args [expr {[lsearch -exact $args -text]+1}]]
                    if {$n == 0} {return [lindex [split $::current .] end]}
                    if {$::native ne "" && ($n == 5 || $n == 9 || $n == 10)} {return 55.00%}
                    return 50.00%
                }
                proc gui_exclusion {args} {if {[lindex $args 0] eq "-reset"} {set ::native {}}}
                proc gui_cov_excl_review {args} {return 1}
                proc gui_exclusion_file {mode flag file} {
                    if {$mode eq "-load"} {set f [open $file r]; set ::native [read $f]; close $f} else {
                        set f [open $file w]; puts -nonewline $f $::native; close $f
                    }
                }
                proc csv_row {f values} {puts $f [join $values ,]}
            ''')
            t.eval(p.HOOK.read_text()); t.call('apply_reviewed_waivers', 'CoverageTable.1')
            self.assertEqual((root / 'raw.csv').read_text(), 'original full raw with UVM\n')
            for stage in ('raw', 'applied', 'reloaded', 'reset'):
                self.assertEqual(len(p.rooted(root / ('rooted_' + stage + '.csv'), names, stage)), 11)
            self.assertEqual((root / 'rooted_applied.csv').read_bytes(), (root / 'summary_waived.csv').read_bytes())
            self.assertEqual(p.records((root / 'applied.el').read_bytes()), p.records(EL))
            for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
                self.assertEqual((root / name).read_bytes(), b'')
            self.assertNotIn('-recursive', p.HOOK.read_text()); self.assertNotIn('lassign', p.HOOK.read_text())

    def test_wrong_selection_and_empty_normalization(self):
        t = tkinter.Tcl(); t.tk.wantobjects(False); t.eval(p.HOOK.read_text())
        self.assertEqual(t.call('p740_tokens', '{{}}'), '')
        t.eval('proc gui_list_get_selected {args} {return {{wrong}}}; proc gui_list_select {args} {}')
        with self.assertRaisesRegex(tkinter.TclError, 'Requested full token'): t.call('p740_select', p.SYSTEM)

    def test_actual_popen_environment_has_DVE_unset(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d); c = dict(command=['never-launch'], timeout=900, pins={}, tool_identity={})
            with patch.object(p, 'verify', return_value=c), patch.object(p.tools, 'controlled_environment',
                    return_value={'DVE': '/sealed/gui/dve', 'VCS_HOME': '/sealed'}), patch.object(
                    p.subprocess, 'Popen', side_effect=RuntimeError('HOST_ONLY')) as launch:
                with self.assertRaisesRegex(RuntimeError, 'HOST_ONLY'): p.run(output, 'fixture')
            self.assertNotIn('DVE', launch.call_args.kwargs['env'])


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.out = self.root / 'fresh'; self.raw = self.root / 'raw'; self.raw.mkdir()
        raw_file(self.raw / 'summary.csv')
        (self.raw / 'inputs.txt').write_text('design\n' + ''.join('test%d\n' % i for i in range(740)))
        (self.raw / 'selected_tests.txt').write_text(''.join('native%d\n' % i for i in range(740)))
        self.result = self.root / 'raw-result.json'
        self.result.write_text(json.dumps(dict(status='VERIFIED_RAW740_HISTORICAL_ONLY', tests=740, waived=False,
            rows=12, report=str(self.raw), pins={str(x): p.sha(x) for x in self.raw.iterdir()})))
        self.els = [self.root / 'six.el', self.root / 'snapshot.el']
        self.els[0].write_bytes(EL); self.els[1].write_bytes(EL.replace(b'Branch 3', b'Branch 4'))
        self.reviews = [self.root / 'audit1.json', self.root / 'audit2.json']
        for path, el in zip(self.reviews, self.els):
            path.write_text(json.dumps(dict(schema='MASK_STORE_SNAPSHOT_COND24_FORMAL740_READONLY_AUDIT_V1',
                status='READONLY_MASK_STORE_COND24_REBIND740_PASS_NOT_APPLICATION', population=740, pins={str(el): p.sha(el)})))
        mock = patch.object(p, 'APPROVED', {p.sha(x): 1 for x in self.els}); mock.start(); self.addCleanup(mock.stop)
        for method, value in (('prepare', dict(files=[], executable='/sealed/dve.exe')),
                              ('launch_command', ['DVE', 'EXPORT']), ('revalidate', None)):
            mock = patch.object(p.tools, method, return_value=value); mock.start(); self.addCleanup(mock.stop)

    def prepare(self):
        p.prepare(self.out, self.result, p.sha(self.result), self.els, self.reviews, [p.sha(x) for x in self.reviews], 900)

    def test_prepare_verify_exact_eleven_bound_selection_no_launch(self):
        self.prepare(); seal = p.sha(self.out / 'config.json'); c = p.verify(self.out, seal)
        self.assertEqual(c['formal_scopes'], list(p.ROOTS)); self.assertFalse(c['full_hierarchy_fresh'])
        self.assertIn(str(self.out / 'root-selection.tcl'), c['pins'])
        t = tkinter.Tcl(); t.eval((self.out / 'root-selection.tcl').read_text())
        self.assertEqual(int(t.eval('llength $p740_scopes')), 11)
        self.assertEqual(int(t.eval('array size p740_root_names')), 11)
        self.assertFalse((self.out / 'execution.json').exists())
        with self.assertRaises(ValueError): self.prepare()

    def test_modified_root_selection_or_config_rejected(self):
        self.prepare(); seal = p.sha(self.out / 'config.json')
        (self.out / 'root-selection.tcl').write_text('set p740_scopes wrong\n')
        with self.assertRaises(ValueError): p.verify(self.out, seal)

    def test_missing_requested_raw_scope_rejected(self):
        path = self.raw / 'summary.csv'; path.write_text(path.read_text().replace(p.SYSTEM, 'other', 1))
        d = json.loads(self.result.read_bytes()); d['pins'][str(path)] = p.sha(path); self.result.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'Missing approved rooted scope'): self.prepare()

    def test_review_or_source_pin_drift_rejected(self):
        path = self.reviews[0]; d = json.loads(path.read_bytes()); d['pins'][str(self.els[0])] = 'a'*64
        path.write_text(json.dumps(d))
        with self.assertRaises(ValueError): self.prepare()


if __name__ == '__main__': unittest.main()
