"""Offline focused mutations and execution of the complete hook with GUI stubs."""
import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import apply_points740_v3 as p

BRANCH = (b'CHECKSUM: "10 20"\nINSTANCE: top.unit\nANNOTATION: "old"\n'
          b'Branch 3 "40" "if (x)" (1) "else"\n')
COND = (b'CHECKSUM: "10 21"\nINSTANCE: top.unit\nANNOTATION: "note"\n'
        b'Condition 7 "50" "(a && b) 1 -1" (3 "11")\n')
EL = BRANCH + COND
HEADER = ['Name', 'Depth', 'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch']


def csv_file(path, percent='50.00%'):
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(HEADER)
        writer.writerow(['top', '0'] + [percent] * 6)
        writer.writerow(['gen.unit', '1'] + ['NA'] * 6)


class NativeTests(unittest.TestCase):
    def test_order_and_annotations_ignored(self):
        self.assertEqual(p.records(EL), p.records((COND + BRANCH).replace(b'old', b'new')))
        self.assertEqual(p.records(EL), p.records(BRANCH + b'\n' + COND))

    def test_empty(self):
        self.assertEqual(p.records(b''), {})

    def test_each_semantic_field_changes(self):
        for before, after in ((b'top.unit', b'top.other'), (b'10 20', b'11 20'),
                              (b'10 20', b'10 22'), (b'Branch 3', b'Branch 4'),
                              (b'"40"', b'"41"'), (b'if (x)', b'if (y)'),
                              (b'(1)', b'(2)'), (b'"else"', b'"then"'),
                              (b'1 -1', b'2 -1'), (b'"11"', b'"01"')):
            with self.subTest(before=before):
                self.assertNotEqual(p.records(EL), p.records(EL.replace(before, after, 1)))

    def test_whole_scope_and_unsupported_rejected(self):
        for raw in (b'CHECKSUM: "10 20"\nINSTANCE: top.unit\n',
                    EL + b'CHECKSUM: "1 2"\n', EL + b'INSTANCE: top.other\n',
                    EL + b'MODULE: any\n', EL + b'RECURSIVE: top\n',
                    EL.replace(b'Branch 3', b'Line 3'), EL + b'UNKNOWN: directive\n', b'\n'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError): p.records(raw)

    def test_duplicates_rejected_not_collapsed(self):
        for raw in (EL + BRANCH, EL + BRANCH.replace(b'"40"', b'"41"')):
            with self.assertRaises(ValueError): p.records(raw)

    def test_distinct_native_points_same_predicate_legal(self):
        self.assertEqual(len(p.records(BRANCH + BRANCH.replace(b'Branch 3', b'Branch 5'))), 2)

    def test_nonascii_partial_and_missing_width(self):
        for raw in (EL + b'\xff', EL[:-1], EL.replace(b' 1 -1', b'')):
            with self.assertRaises((ValueError, UnicodeError)): p.records(raw)

    def test_pin_conflict_and_actual_file_drift(self):
        with self.assertRaises(ValueError): p.merge({'a': 'a'*64}, {'a': 'b'*64})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'pin'; path.write_bytes(b'original')
            pins = {str(path): p.sha(path)}; p.check_pins(pins)
            path.write_bytes(b'drift')
            with self.assertRaises(ValueError): p.check_pins(pins)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'out'; self.output.mkdir()
        self.report = Path(self.temp.name) / 'raw'; self.report.mkdir()
        self.c = dict(records=2, inputs=['design', 'test'], selected_tests=['test/native'],
                      report=str(self.report), pins={}, tool_identity=dict(executable='/sealed/dve.exe'))
        live = dict(executable_verified=True, executable='/sealed/dve.exe', pid=10)
        (self.output / 'live-identity.json').write_text(json.dumps(live))
        (self.output / 'terminal.json').write_text(json.dumps(dict(returncode=0, live_identity=live)))
        (self.output / 'DVEfiles').mkdir()
        for name in ('points.el', 'applied.el', 'reloaded.el'):
            (self.output / name).write_bytes(EL)
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
            (self.output / name).write_bytes(b'')
        (self.output / 'inputs.txt').write_text('design\ntest\n')
        (self.output / 'selected_tests.txt').write_text('test/native\n')
        (self.output / 'run.log').write_text('normal\n')
        (self.output / 'DVEfiles/dve_gui.log').write_text(
            'DVE_SELECTED_TESTS: test/native\nPOINT740_APPLIED_RELOADED_RESET_DONE\nDVE_COVERAGE_EXPORT_DONE\n')
        csv_file(self.report / 'summary.csv')
        for name in ('raw.csv', 'reset.csv'): csv_file(self.output / name)
        for name in ('applied.csv', 'reloaded.csv'): csv_file(self.output / name, '60.00%')
        self.normalize_applied_metrics()
        self.identity = patch.object(p.tools, 'revalidate'); self.identity.start(); self.addCleanup(self.identity.stop)

    def normalize_applied_metrics(self):
        for name in ('applied.csv', 'reloaded.csv'):
            path = self.output / name
            with path.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                if row['Name'] == 'top':
                    for metric in p.PROTECTED_METRICS:
                        row[metric] = '50.00%'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=HEADER)
                writer.writeheader(); writer.writerows(rows)

    def test_exact_qt_allowance_recorded_not_removed_from_files(self):
        for name in ('run.log', 'DVEfiles/dve_gui.log', 'DVEfiles/dve_qtwarnings.log', 'diagnostics.txt'):
            path = self.output / name
            old = path.read_text() if path.exists() else ''
            path.write_text(old + p.KNOWN_QT + '\n')
        evidence = p.inspect(self.c, self.output)['diagnostics']
        self.assertEqual(evidence['allowlist'], [p.KNOWN_QT])
        self.assertEqual(len(evidence['observed_allowed_lines']), 4)
        for observation in evidence['observed_allowed_lines']:
            self.assertEqual(observation['exact_line'], p.KNOWN_QT)
            self.assertIn(p.KNOWN_QT, Path(observation['path']).read_text())

    def test_near_match_and_extra_warning_error_rejected(self):
        path = self.output / 'DVEfiles/dve_qtwarnings.log'
        for value in (p.KNOWN_QT + ' extra', 'prefix ' + p.KNOWN_QT,
                      p.KNOWN_QT.lower(), p.KNOWN_QT.replace('Double', 'Triple'),
                      p.KNOWN_QT + '\nWarning: license', p.KNOWN_QT + '\nError: import',
                      p.KNOWN_QT + '\nrejected point'):
            with self.subTest(value=value):
                path.write_text(value + '\n')
                with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_error_in_primary_log_after_exact_qt_rejected(self):
        path = self.output / 'run.log'
        path.write_text(p.KNOWN_QT + '\nerror importing EL\n')
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_each_protected_metric_each_stage_and_each_row(self):
        originals = {name: (self.output / name).read_text() for name in ('applied.csv', 'reloaded.csv')}
        for name in originals:
            for metric in p.PROTECTED_METRICS:
                for row_index in (0, 1):
                    for path_name, text in originals.items():
                        (self.output / path_name).write_text(text)
                    path = self.output / name
                    with path.open(newline='') as stream:
                        rows = list(csv.DictReader(stream))
                    rows[row_index][metric] = '51.00%'
                    # Change both stages identically so equality alone cannot pass.
                    for stage in originals:
                        with (self.output / stage).open('w', newline='') as stream:
                            writer = csv.DictWriter(stream, fieldnames=HEADER)
                            writer.writeheader(); writer.writerows(rows)
                    with self.subTest(stage=name, metric=metric, row=row_index):
                        with self.assertRaisesRegex(ValueError, 'Protected metric drift'):
                            p.inspect(self.c, self.output)

    def test_protected_metric_evidence_all_rows(self):
        result = p.inspect(self.c, self.output)
        self.assertEqual(result['protected_metrics'], ['Line', 'Toggle', 'FSM'])
        self.assertEqual(result['protected_row_metric_checks'], 12)

    def test_good_terminal_and_dotted_lazy_name(self):
        self.assertEqual(p.inspect(self.c, self.output)['records'], 2)

    def test_reordered_saved_semantics(self):
        (self.output / 'reloaded.el').write_bytes((COND + BRANCH).replace(b'old', b'new'))
        p.inspect(self.c, self.output)

    def test_missing_extra_and_checksum_drift(self):
        for raw in (BRANCH, EL.replace(b'"50"', b'"51"'), EL + BRANCH):
            (self.output / 'applied.el').write_bytes(raw)
            with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_each_empty_guard(self):
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
            path = self.output / name; path.write_bytes(BRANCH)
            with self.assertRaises(ValueError): p.inspect(self.c, self.output)
            path.write_bytes(b'')

    def test_raw_and_reset_numeric_drift(self):
        for name in ('raw.csv', 'reset.csv'):
            csv_file(self.output / name, '49.00%')
            with self.assertRaises(ValueError): p.inspect(self.c, self.output)
            csv_file(self.output / name)

    def test_reload_or_hierarchy_drift(self):
        csv_file(self.output / 'reloaded.csv', '61.00%')
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)
        csv_file(self.output / 'reloaded.csv', '60.00%')
        self.normalize_applied_metrics()
        for name in ('applied.csv', 'reloaded.csv'):
            path = self.output / name; path.write_text(path.read_text().replace('gen.unit', 'other'))
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_actual_membership_and_rejected(self):
        (self.output / 'selected_tests.txt').write_text('wrong/native\n')
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)
        (self.output / 'selected_tests.txt').write_text('test/native\n')
        (self.output / 'rejected_tests.txt').write_text('')
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_warning_rejected_error_no_exit0_override(self):
        for value in ('Warning license', 'rejected native', 'Error command', 'FAILED', 'Fatal'):
            (self.output / 'run.log').write_text(value)
            with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_qt_warning_no_silent_exception(self):
        (self.output / 'DVEfiles/dve_qtwarnings.log').write_text('QWarning: unexpected\n')
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_missing_duplicate_markers(self):
        path = self.output / 'DVEfiles/dve_gui.log'; original = path.read_text()
        for text in (original.replace('DVE_COVERAGE_EXPORT_DONE\n', ''), original + 'DVE_COVERAGE_EXPORT_DONE\n'):
            path.write_text(text)
            with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_logged_membership(self):
        path = self.output / 'DVEfiles/dve_gui.log'; path.write_text(path.read_text().replace('test/native', 'wrong'))
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_terminal_pin_drift(self):
        path = self.report / 'summary.csv'; self.c['pins'] = {str(path): 'a'*64}
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_terminal_nonzero_and_unverified_executable(self):
        path = self.output / 'terminal.json'; original = json.loads(path.read_bytes())
        state = dict(original, returncode=124); path.write_text(json.dumps(state))
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)
        path.write_text(json.dumps(original))
        live = original['live_identity']; live['executable_verified'] = False
        (self.output / 'live-identity.json').write_text(json.dumps(live))
        path.write_text(json.dumps(dict(returncode=0, live_identity=live)))
        with self.assertRaises(ValueError): p.inspect(self.c, self.output)

    def test_bad_csv_depth_duplicate_and_percentage(self):
        path = self.output / 'raw.csv'; good = path.read_text()
        for text in (good.replace('gen.unit,1', 'gen.unit,9'), good + good.splitlines()[1] + '\n',
                     good.replace('50.00%', '101.00%')):
            path.write_text(text)
            with self.assertRaises(ValueError): p.table(path)


class TclTests(unittest.TestCase):
    def test_complete_hook_actual_host_tcl(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); t = tkinter.Tcl(); t.setvar('env(DVE_COVERAGE_OUTPUT)', d)
            (root / 'summary.csv.partial').write_text('raw fixture\n')
            (root / 'points.el').write_bytes(EL)
            t.eval('''
                set state {}; set operations {}
                proc gui_exclusion_file {mode option file} {
                    global state operations
                    lappend operations [list $mode [file tail $file]]
                    if {$mode eq "-load"} {
                        set f [open $file r]; set state [read $f]; close $f
                    } else {set f [open $file w]; puts -nonewline $f $state; close $f}
                }
                proc gui_exclusion {args} {
                    global state refresh
                    if {[lindex $args 0] eq "-reset"} {set state {}}
                    if {[info exists refresh] && [llength $refresh] == 5} {lappend refresh recalculate}
                }
                proc gui_cov_excl_review {arg} {return 1}
                set refresh {}; set refresh_reads 0
                proc gui_covtable_show {args} {global refresh; set refresh [list show]}
                proc gui_covtable_setroot {args} {global refresh; lappend refresh setroot}
                proc gui_list_expand {args} {global refresh; lappend refresh expand}
                proc gui_cov_show_value {args} {global refresh; lappend refresh percentage}
                proc gui_process_events {args} {global refresh; lappend refresh events}
                proc gui_list_get {args} {
                    if {[lindex $args end] eq "-firstChild"} {return rootHandle}
                    if {[lsearch -exact $args -path] >= 0} {return ara_tb}
                    error "unknown root query"
                }
                proc gui_list_get_property {args} {
                    set n [lindex $args end]
                    if {$n == 5} {return Line}; error "end"
                }
                proc csv_row {f values} {puts $f [join $values ,]}
                proc export_rows {f id parent depth columns} {
                    global row_count refresh refresh_reads
                    if {$refresh ne "show setroot expand percentage events recalculate events"} {error "Stale hierarchy read"}
                    incr refresh_reads
                    puts $f "top,0,50.00%"; set row_count 1
                }
            ''')
            t.eval(p.HOOK.read_text()); t.call('apply_reviewed_waivers', 'CoverageTable.1')
            self.assertEqual((root / 'raw.csv').read_text(), 'raw fixture\n')
            for name in ('applied.el', 'reloaded.el'): self.assertEqual(p.records((root / name).read_bytes()), p.records(EL))
            for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
                self.assertEqual((root / name).read_bytes(), b'')
            for name in ('applied.csv', 'reloaded.csv', 'reset.csv'): self.assertTrue((root / name).is_file())
            self.assertEqual(int(t.getvar('refresh_reads')), 3)
            self.assertNotIn('gui_exclude_items', p.HOOK.read_text())
            self.assertNotIn('-recursive', p.HOOK.read_text())
            self.assertNotIn('lassign', p.HOOK.read_text())
            self.assertNotIn('{*}', p.HOOK.read_text())

    def test_hook_cleanup_on_import_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'summary.csv.partial').write_text('raw\n')
            t = tkinter.Tcl(); t.setvar('env(DVE_COVERAGE_OUTPUT)', d)
            t.eval('''
                proc gui_exclusion_file {mode option file} {
                    if {$mode eq "-save"} {close [open $file w]}
                }
                proc gui_cov_excl_review {args} {return 0}
                proc gui_exclusion {args} {}
            ''')
            t.eval(p.HOOK.read_text())
            with self.assertRaises(tkinter.TclError): t.call('apply_reviewed_waivers', 'CoverageTable.1')
            self.assertTrue((root / 'cleanup-empty.el').is_file())


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.output = self.root / 'fresh'
        self.report = self.root / 'raw'; self.report.mkdir()
        (self.report / 'inputs.txt').write_text('design\n' + ''.join('vdb%d\n' % n for n in range(740)))
        (self.report / 'selected_tests.txt').write_text(''.join('native%d\n' % n for n in range(740)))
        csv_file(self.report / 'summary.csv')
        self.raw = self.root / 'raw-result.json'
        self.els = [self.root / 'six.el', self.root / 'snapshot.el']
        for path, data in zip(self.els, (BRANCH, COND)): path.write_bytes(data)
        self.raw.write_text(json.dumps(dict(status='VERIFIED_RAW740_HISTORICAL_ONLY', tests=740, waived=False,
            rows=2, report=str(self.report), pins={str(x): p.sha(x) for x in self.report.iterdir()})))
        self.reviews = [self.root / 'review-six.json', self.root / 'review-snapshot.json']
        self.audits = [dict(schema='MASK_STORE_SNAPSHOT_COND24_FORMAL740_READONLY_AUDIT_V1',
                           status='READONLY_MASK_STORE_COND24_REBIND740_PASS_NOT_APPLICATION', population=740,
                           pins={str(path): p.sha(path)}) for path in self.els]
        for path, audit in zip(self.reviews, self.audits): path.write_text(json.dumps(audit))
        allowed = patch.object(p, 'APPROVED', {p.sha(x): 1 for x in self.els})
        allowed.start(); self.addCleanup(allowed.stop)
        identity = dict(files=[], executable='/sealed/dve.exe')
        for method, value in (('prepare', identity), ('launch_command', ['DVE', 'EXPORT']), ('revalidate', None)):
            mock = patch.object(p.tools, method, return_value=value); mock.start(); self.addCleanup(mock.stop)

    def prepare(self, **changes):
        args = dict(output=self.output, raw_result=self.raw, raw_seal=p.sha(self.raw), els=self.els,
                    reviews=self.reviews, review_seals=[p.sha(x) for x in self.reviews], timeout=900)
        args.update(changes); p.prepare(**args)

    def test_prepare_verify_no_launch_exact_pins(self):
        self.prepare()
        config = p.verify(self.output, p.sha(self.output / 'config.json'))
        self.assertEqual(config['records'], 2)
        self.assertFalse((self.output / 'execution.json').exists())
        self.assertIn(str(p.HOOK), config['pins'])
        self.assertIn(str(p.EXPORT), config['pins'])
        with self.assertRaises(ValueError): self.prepare()

    def test_no_silent_input_population_or_el_drift(self):
        self.els[0].write_bytes(BRANCH.replace(b'"40"', b'"41"'))
        with self.assertRaises(ValueError): self.prepare()
        self.els[0].write_bytes(BRANCH)
        state = json.loads(self.raw.read_bytes()); state['tests'] = 739
        self.raw.write_text(json.dumps(state))
        with self.assertRaises(ValueError): self.prepare()

    def test_review_population_status_and_unbound_el(self):
        for key, value in (('status', 'HOLD'), ('status', 'FAIL'), ('status', 'PASS_BUT_HOLD'),
                           ('pins', {}), ('population', 735)):
            self.reviews[0].write_text(json.dumps(dict(self.audits[0], **{key: value})))
            with self.assertRaises(ValueError): self.prepare()

    def test_external_review_seal_and_missing_group(self):
        with self.assertRaises(ValueError): self.prepare(review_seals=['a'*64, p.sha(self.reviews[1])])
        with self.assertRaises(ValueError): self.prepare(reviews=self.reviews[:1], review_seals=[p.sha(self.reviews[0])])
        with self.assertRaises(ValueError): self.prepare(els=[self.els[0], self.els[0]])

    def test_actual_six_schema_and_protection_conflict(self):
        audit = dict(schema='SIX_POLICY_FORMAL740_ELIGIBILITY_AUDIT_V1',
                     status='EXACT_SIX_POLICY_740_ELIGIBLE_NOT_APPLIED',
                     review=dict(tests=740, unique_targets=5808, cross_target_protection_conflicts=0),
                     evidence_pins=self.audits[0]['pins'])
        self.reviews[0].write_text(json.dumps(audit)); self.prepare()
        audit['review']['cross_target_protection_conflicts'] = 1
        self.reviews[0].write_text(json.dumps(audit))
        with self.assertRaises(ValueError): p.reviewed_inputs(self.els, self.reviews, [p.sha(x) for x in self.reviews])

    def test_parent_source_pin_drift(self):
        extra = self.root / 'frozen-source'; extra.write_bytes(b'actual')
        self.audits[0]['pins'][str(extra)] = 'a'*64
        self.reviews[0].write_text(json.dumps(self.audits[0]))
        with self.assertRaises(ValueError): self.prepare()

    def test_short_budget_only(self):
        with self.assertRaises(ValueError): self.prepare(timeout=14400)


class V3Tests(unittest.TestCase):
    def test_refresh_sequence_identical_mature_commands_before_column_reads(self):
        body = p.HOOK.read_text()
        start = body.index('proc p740_csv')
        end = body.index('proc p740_session')
        csv_body = body[start:end]
        previous = -1
        for command in ('gui_covtable_show -id $id -show {Design Hierarchy} -cumulative 1',
                        'gui_covtable_setroot -id $id ara_tb',
                        'gui_list_expand -id $id -all {<root>}',
                        'gui_cov_show_value -switch false',
                        'gui_process_events -mstime 100',
                        'gui_exclusion -id $id -recalculate',
                        'gui_process_events -mstime 100',
                        'gui_list_get_property', 'export_rows'):
            current = csv_body.find(command, previous + 1)
            self.assertGreater(current, previous)
            previous = current

    def test_unknown_or_local_root_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as d:
            t = tkinter.Tcl(); t.setvar('env(DVE_COVERAGE_OUTPUT)', d)
            t.eval("""
                proc gui_covtable_show {args} {}
                proc gui_covtable_setroot {args} {}
                proc gui_list_expand {args} {}
                proc gui_cov_show_value {args} {}
                proc gui_process_events {args} {}
                proc gui_list_get {args} {
                    if {[lindex $args end] eq "-firstChild"} {return rootHandle}
                    return i_system
                }
            """)
            t.eval(p.HOOK.read_text())
            with self.assertRaisesRegex(tkinter.TclError, 'Full-root GUI contract differs'):
                t.call('p740_csv', 'CoverageTable.1', 'applied.csv')
            self.assertFalse((Path(d) / 'applied.csv').exists())

    def test_actual_run_popen_environment_has_no_entry_DVE(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            config = dict(command=['never-launch'], timeout=900, pins={}, tool_identity={})
            with patch.object(p, 'verify', return_value=config), patch.object(
                    p.tools, 'controlled_environment', return_value={'DVE': '/sealed/gui/dve', 'VCS_HOME': '/sealed'}), patch.object(
                    p.subprocess, 'Popen', side_effect=RuntimeError('HOST_TEST_NO_PROCESS')) as launch:
                with self.assertRaisesRegex(RuntimeError, 'HOST_TEST_NO_PROCESS'):
                    p.run(output, 'fixture-seal')
            env = launch.call_args.kwargs['env']
            self.assertNotIn('DVE', env)
            self.assertEqual(env['VCS_HOME'], '/sealed')
            self.assertEqual(env['DVE_REVIEWED_WAIVERS'], str(p.HOOK))
            self.assertEqual(env['DVE_COVERAGE_OUTPUT'], str(output))
            self.assertEqual(json.loads((output / 'status.json').read_bytes())['status'], 'HOLD')


if __name__ == '__main__': unittest.main()


