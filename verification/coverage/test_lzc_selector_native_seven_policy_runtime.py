import ast
import copy
import csv
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import lzc_selector_native_seven_policy_runtime as subject


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((subject.frozen.OUT / 'lzc-selector-native-seven-policy-plan-723-20261006-01/application-plan.json').read_bytes())
        cls.six_output = Path(cls.plan['six_config']).parent

    def tcl(self, script):
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, check=True)
        self.assertEqual(result.stderr, '', result.stderr)
        return result.stdout

    def test_exact4200_60_true_no_op16_or_branch_target(self):
        positions = subject.target_positions(self.plan)
        self.assertEqual(len(positions), 60)
        self.assertTrue(all(self.plan['exact_lzc_protection_rows'][i]['metric'] == 'cond'
                            and self.plan['exact_lzc_protection_rows'][i]['vector'] == '1' for i in positions))
        bad = copy.deepcopy(self.plan)
        bad['condition_native_records'][0]['vector'] = '0'
        with self.assertRaises(ValueError):
            subject.target_positions(bad)

    def test_all_lzc_state_identity_and_protection_rejection(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            path = Path(temporary) / 'states.tsv'
            selected = set(subject.target_positions(self.plan))
            def write(active, changed=None):
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=['position', 'scope', 'metric', 'native_id', 'expression', 'vector', 'excluded'], delimiter='\t')
                    writer.writeheader()
                    for i, row in enumerate(self.plan['exact_lzc_protection_rows']):
                        item = {k: v or '' for k, v in row.items()}
                        item.update(position=str(i), excluded=str(int(active and i in selected)))
                        if changed and i == changed[0]:
                            item.update(changed[1])
                        writer.writerow(item)
            for stage in subject.STAGES:
                active = stage in ('selected', 'reloaded', 'after-root')
                write(active)
                self.assertEqual(subject.read_lzc_states(path, self.plan, active), 4200)
            for changed in ((0, {'excluded': '1'}), (0, {'native_id': '9999'}),
                            (selected.pop(), {'excluded': '0'})):
                write(True, changed)
                with self.assertRaises(ValueError):
                    subject.read_lzc_states(path, self.plan, True)

    def test_narrow_metrics_not_global_condition_or_branch_permission(self):
        allow = lambda scope, metric: subject.change_allowed(scope, metric, {'top.six.child'}, {'top.lzc.child'})
        self.assertTrue(allow('top', 'Condition'))
        self.assertTrue(allow('top.six', 'Branch'))
        self.assertTrue(allow('top.lzc', 'Score'))
        for scope, metric in [('top.lzc', 'Branch'), ('top.six', 'Condition'), ('top.other', 'Score'),
                              ('top', 'Line'), ('top', 'FSM'), ('top', 'Toggle'), ('top.lzc.child.other', 'Condition')]:
            self.assertFalse(allow(scope, metric))

    def test_exact_ast_adapter_retains_frozen_checks(self):
        check = subject.seven_verifier({}, lambda *_: False)
        self.assertEqual(check.__code__.co_argcount, subject.frozen.verify_artifacts.__code__.co_argcount)
        self.assertIn('seven_change_allowed', check.__code__.co_names)
        self.assertIn('product_geometry_match', check.__code__.co_names)
        self.assertIn('rooted_rows', check.__code__.co_names)
        self.assertIn('bindings', check.__code__.co_names)
        self.assertIn('Missing after-root all-point audit', inspect.getsource(subject.frozen.verify_artifacts))
        ast.parse(inspect.getsource(subject.frozen.verify_artifacts))

    def test_library_initialization_actual_frozen_helpers_no_eda_and_real_reload_order(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            for name in subject.HELPERS:
                (root / name).write_bytes((self.six_output / name).read_bytes())
            (root / 'six-library.tcl').write_text(subject.six_library())
            (root / 'seven-selection.tcl').write_text(subject.selection_text(self.plan))
            script = '''
set seven_library_only 1
set env(DVE_COVERAGE_OUTPUT) {%s}
source {%s}
proc gui_open_cov {args} {error UNAPPROVED_OPEN}
proc gui_exit {args} {error UNAPPROVED_EXIT}
seven_initialize
if {$seven_before_complete != 0} {error OPEN_GATE}
if {![catch {seven_load {arbitrary.el}}]} {error MISSING_CLOSED_GATE}
set body [info body qbsapp_session]
set index [string first {qbsapp_summary applied} $body]
if {$index < 0} {error MISSING_TAIL}
set tail [string range $body $index end]
set calls {}
set native_state 1
proc qbsapp_root {} {}
proc qbsapp_summary {stage} {global calls; lappend calls summary:$stage}
proc qbs_audit {stage active} {
    global calls native_state
    if {$active != $native_state} {error WRONG_NATIVE_STATE}
    lappend calls audit:$stage
}
proc dbg_save {name args} {
    global env native_state calls
    set path [file join $env(DVE_COVERAGE_OUTPUT) $name]
    set stream [open $path w]
    if {$native_state} {puts -nonewline $stream {exact5868}}
    close $stream
    lappend calls save:$name
}
proc gui_exclusion {args} {
    global native_state calls
    if {$args eq {-reset}} {set native_state 0; lappend calls reset}
}
proc gui_exclusion_file {args} {
    global native_state calls
    if {[lindex $args 0] ne "-load" || $native_state != 0} {error BAD_LOAD_ORDER}
    set native_state 1
    lappend calls load
}
proc gui_cov_excl_review {args} {return 1}
dbg_save applied.el
set calls {}
set seven_before_complete 1
eval $tail
if {$calls ne {summary:applied reset audit:reset save:reset-empty.el summary:reset load audit:reloaded save:reloaded.el audit:after-root save:after-root.el reset save:session-final-empty.el}} {error "ORDER $calls"}
if {$native_state != 0} {error NOT_RESET}
puts STATIC_SESSION_OK
''' % (root, subject.TCL)
            self.assertIn('STATIC_SESSION_OK', self.tcl(script))

    def test_tcl_full4200_audit_rejects_protected_change_and_before_gate(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            (root / 'lzc').mkdir()
            (root / 'seven-selection.tcl').write_text(subject.selection_text(self.plan))
            script = '''
set seven_library_only 1
source {%s}
proc lpd_require {ok message} {if {!$ok} {error $message}}
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set active 0
set corrupted -1
proc gui_cov_show_cond_ids {args} {}
proc qbsapp_root {} {}
proc lpb_row {row} {global position; set position [lindex $row 5]; return vector}
proc gui_exclusion {args} {
    global position active seven_target_positions corrupted
    if {$position == $corrupted} {return 1}
    return [expr {$active && [lsearch -exact $seven_target_positions $position] >= 0}]
}
seven_lzc_audit before 0
set active 1
seven_lzc_audit selected 1
set corrupted 0
if {![catch {seven_lzc_audit broken 1} message]} {error NO_PROTECTION_REJECTION}
if {$message ne "Seventh target/protected state differs"} {error WRONG_REJECTION}
puts FULL4200_STUB_OK
''' % (subject.TCL, root / 'seven-selection.tcl', root)
            self.assertIn('FULL4200_STUB_OK', self.tcl(script))

    def test_no_unsupported_expansion_no_builtin_rename(self):
        dependencies = [subject.TCL, subject.six.prior.TCL,
                        subject.SCRIPT.with_name('lzc_selector_native_product_audit_visibility.tcl'),
                        subject.SCRIPT.with_name('lzc_selector_native_product_batch.tcl'),
                        subject.SCRIPT.with_name('lzc_selector_native_product_discover.tcl')]
        for path in dependencies:
            text = path.read_text()
            self.assertNotIn('{*}', text)
            self.assertNotRegex(text, r'rename\s+gui_')
        self.assertNotIn('gui_exit', subject.six_library())

    def test_723_rejected_724_contract_preserves_false_flags(self):
        cfg = json.loads((self.six_output / 'config.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'Fresh724'):
            subject.contract(self.plan, cfg)
        cfg['population'] = 724
        plan = dict(self.plan, population=724)
        subject.contract(plan, cfg)
        for key, value in [('native_X_semantics_measured', True), ('branch_hold', 0),
                           ('op16', 'APPROVED'), ('total_audited_positions', 23569)]:
            with self.assertRaises(ValueError):
                subject.contract(dict(plan, **{key: value}), cfg)

    def test_prepare_check_sealed_chain_no_eda_reject_drift_and_omitted_pin(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            six_root, plan_root = root / 'six', root / 'plan'
            six_root.mkdir()
            plan_root.mkdir()
            cfg = json.loads((self.six_output / 'config.json').read_bytes())
            cfg.update(population=724, output=str(six_root), pins={})
            for name in (*subject.HELPERS, 'combined.el'):
                target = six_root / name
                target.write_bytes((self.six_output / name).read_bytes())
                cfg['pins'][str(target)] = subject.frozen.sha(target)
            subject.frozen.write(six_root / 'config.json', cfg)
            cfg_seal = subject.frozen.sha(six_root / 'config.json')
            proposal = plan_root / 'combined-seven-proposal.el'
            proposal.write_bytes((Path(self.plan['six_config']).parent / 'combined.el').read_bytes() +
                                 (Path(self.plan['source_proof']).parent / 'candidate60.el').read_bytes())
            plan = dict(self.plan, population=724, six_config=str(six_root / 'config.json'),
                        six_config_sha256=cfg_seal, pins={str(subject.BINDINGS): subject.frozen.sha(subject.BINDINGS),
                                                        str(proposal): subject.frozen.sha(proposal)})
            subject.frozen.write(plan_root / 'application-plan.json', plan)
            plan_seal = subject.frozen.sha(plan_root / 'application-plan.json')
            output = subject.frozen.OUT / (root.name + '-runtime')
            try:
                with patch.object(subject.six, 'read_config', return_value=(None, cfg)), \
                     patch.object(subprocess, 'Popen', side_effect=AssertionError('NO_EDA')):
                    with self.assertRaisesRegex(ValueError, 'parent acceptance'):
                        subject.prepare(output, six_root, cfg_seal, plan_root, plan_seal)
                    subject.prepare(output, six_root, cfg_seal, plan_root, plan_seal, True)
                    seal = subject.frozen.sha(output / 'runtime-plan.json')
                    _, derived = subject.read_config(output, seal)
                    self.assertEqual(derived['groups'], cfg['groups'])
                    self.assertEqual(derived['inputs'], cfg['inputs'])
                    self.assertEqual(derived['plan']['input_membership'], cfg['plan']['input_membership'])
                    self.assertEqual(derived['command'][-1], str(subject.TCL))
                    runtime = json.loads((output / 'runtime-plan.json').read_bytes())
                    del runtime['pins'][str(subject.TCL)]
                    subject.frozen.write(output / 'runtime-plan.json', runtime)
                    with self.assertRaisesRegex(ValueError, 'dependency omitted'):
                        subject.read_config(output, subject.frozen.sha(output / 'runtime-plan.json'))
                    (output / 'seven-selection.tcl').write_text('DRIFT')
                    with self.assertRaisesRegex(ValueError, 'pin drift'):
                        subject.read_config(output, subject.frozen.sha(output / 'runtime-plan.json'))
            finally:
                import shutil
                if output.exists():
                    shutil.rmtree(output)


if __name__ == '__main__':
    unittest.main()
