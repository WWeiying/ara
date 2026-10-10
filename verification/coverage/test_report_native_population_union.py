import copy
import json
from pathlib import Path
import subprocess
from types import FunctionType, SimpleNamespace
import unittest
from unittest.mock import patch

import report_native_population_union as report
import test_report_native_combo745 as old_tests


def actual_hook_regression(selection, config):
    """Execute real entry/selection, modeled GUI interfaces, all five stages once."""
    selection_bytes = selection.read_bytes()
    atom = report.frozen.prior.old.base.capture.tcl_atom
    identities = {}
    for group in config['toggle_groups']:
        identities[group['scope']] = group['reference']
    for key, refs in [('queue_config', 'queue_references'), ('diagnostic_config', 'diagnostic_references'),
                      ('child_config', 'child_references')]:
        for instance, rows in zip(config[key]['instances'], config[refs]):
            scope = instance['scope']
            if scope in identities:
                report.require(sorted(identities[scope]) == sorted(rows), 'Shared scope inventory differs')
            identities[scope] = rows
    model = ''
    for scope, rows in identities.items():
        model += 'set %s [list %s]\n' % (atom('::sim_rows(' + scope + ')'), ' '.join(
            '[list %s]' % ' '.join(map(atom, row)) for row in rows))
    for root in config['hierarchy_roots']:
        model += 'set %s %s\n' % (atom('::sim_root_names(' + root['scope'] + ')'), atom(root['name']))
    proxy = SimpleNamespace(TCL=report.TCL, HERE=report.HERE, STAGES=report.frozen.prior.STAGES,
                            dict_rows=report.frozen.prior.dict_rows)
    namespace = dict(old_tests.__dict__, report=proxy)
    original_write, original_run = Path.write_text, subprocess.run
    evidence = {}
    class Done(Exception):
        pass
    def write(path, text, *args, **kwargs):
        if path.name == 'selection.tcl':
            text = selection_bytes.decode('ascii')
        return original_write(path, text, *args, **kwargs)
    def run(*args, **kwargs):
        script = kwargs['input']
        script = script.replace('proc combo_inventory {args} {}', '')
        index = script.index('gui_open_cov\nset failed')
        # The native FSM/DWC audit engines are interface stubs in this host-only
        # exercise. Real Toggle walks and full production session flow execute.
        script = script[:index] + model + r'''
rename source host_original_source
proc combo_dwc_primitives {} {proc ::dw_audit {args} {}}
proc source {path} {
    set result [uplevel 1 [list host_original_source $path]]
    if {[file tail $path] eq "qualify_dwc_points742.tcl"} {proc ::dw_audit {args} {}}
    return $result
}
proc gui_list_action {args} {
    set ::metric [lindex $args end-1]
    set ::scope [lindex $args end]
}
proc gui_list_get {args} {
    set detail [expr {[lindex $args 1] eq "CovDetail.1"}]
    if {[lsearch -exact $args -firstChild] >= 0} {
        return [expr {[lindex $args end] eq "-firstChild" ? 1 : 0}]
    }
    if {[lsearch -exact $args -nextSibling] >= 0} {
        set next [expr {[lindex $args end]+1}]
        if {$detail && $next <= [llength $::sim_rows($::scope)]} {return $next}
        return 0
    }
    if {$detail} {
        set row [lindex $::sim_rows($::scope) [expr {[lindex $args end]-1}]]
        if {[lsearch -exact $args -path] >= 0} {return [lindex $row 0]}
        if {[lsearch -exact $args -meta] >= 0} {return [lindex $row 1]}
        set ix [lsearch -exact $args -text]
        set col [lindex $args [expr {$ix+1}]]
        if {$col == 0} {return [lindex $row 2]}
        return 0
    }
    if {[info exists ::sim_root_names($::root)]} {set label $::sim_root_names($::root)} else {
        set label [lindex [split $::root .] end]
    }
    if {[lsearch -exact $args -path] >= 0} {return $label}
    if {[lsearch -exact $args -meta] >= 0} {return reg}
    set ix [lsearch -exact $args -text]
    set col [lindex $args [expr {$ix+1}]]
    if {$col == 0} {return $label}
    return [expr {50+$::active}]
}
''' + script[index:]
        result = original_run(*args, **dict(kwargs, input=script))
        report.require(not result.stderr and 'RESULT 0 1' in result.stdout and 'NO_STANDALONE 1' in result.stdout,
                       'Actual generated entry GUI-stub flow failed: ' + result.stderr + result.stdout)
        # Find the isolated test output from its environment declaration.
        import re
        out = Path(re.search(r'set ::env\(DVE_COVERAGE_OUTPUT\) \{([^}]+)\}', script)[1])
        for prefix, refs in [('native', config['queue_references']),
                             ('diagnostic', config['diagnostic_references']), ('child', config['child_references'])]:
            report.audit_six(out, prefix, refs)
        for index, group in enumerate(config['toggle_groups']):
            for stage in report.STAGES:
                rows = report.table(out / ('combo_%s_%d.tsv' % (stage, index)), ['handle', 'path', 'meta', 'name'])
                report.require(sorted(rows) == sorted(group['reference']), 'Host full Toggle complement differs')
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
            report.require((out / name).read_bytes() == b'', 'Host reset not empty')
        for name in ('applied.el', 'reloaded.el'):
            report.require((out / name).read_bytes() == b'NATIVE_UNION\n', 'Host save/reload differs')
        for stage in report.frozen.prior.STAGES:
            rows = report.frozen.prior.dict_rows(out / ('modules_' + stage + '.csv'))
            report.require([(r['Scope'], r['Name']) for r in rows] ==
                           [(r['scope'], r['name']) for r in config['hierarchy_roots']],
                           'Host rooted scope/name ordering differs')
        evidence.update(status='ACTUAL_GENERATED_SELECTION_AND_ENTRY_GUI_STUB_FIVE_STAGE_PASS',
            design_loads=1, stages=list(report.STAGES), toggle_groups=len(config['toggle_groups']),
            native_GUI_measured=False, FSM_DWC_audit_stubs=True, EDA_launched=False)
        raise Done()
    test = FunctionType(old_tests.HookTests.test_actual_proc_import_and_full_hook_five_stages.__code__, namespace)
    with patch.object(Path, 'write_text', write), patch.object(subprocess, 'run', run):
        try:
            test(unittest.TestCase())
        except Done:
            pass
    report.require(evidence, 'Host hook not executed')
    return evidence


def fixture():
    c = json.loads((report.BASE / 'config.json').read_bytes())
    c.update(child_config=json.loads((report.CHILD / 'config.json').read_bytes()),
             cast_config=json.loads((report.CAST / 'config.json').read_bytes()),
             fma_mode='retained108', active_fma_config=c['fma_config'])
    fscopes = {i['scope'] for i in c['fma_config']['instances']}
    c['legacy_fma_el'] = ''.join(b for s, b in report.blocks((report.BASE / 'applied.el').read_text()) if s in fscopes)
    text = (report.BASE / 'applied.el').read_text() + (report.CHILD / 'first.el').read_text() + (report.CAST / 'first.el').read_text()
    return c, text


class UnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.text = fixture()

    def test_actual_qualified_canonical_union(self):
        value = report.records(self.text, self.c)
        self.assertEqual(len(value['fma']), 108)
        self.assertEqual(len(value['cast168']), 168)
        self.assertEqual(len(value['child15']), 798)
        self.assertEqual(value['retained']['prior']['original']['prior'][2], [])
        report.ownership(self.c)

    def expanded_fixture(self):
        out = report.life.OUT / 'fma_expanded_native_612-agent-20261007-04'
        q = report.life.read_bound(out / 'capture-result.json',
            'b07201c920d2a952f08d263758cd54c4d5093e5eeac81a419d4512f2e8f7b492')
        config = report.life.read_bound(out / 'config.json', q['config_seal'])
        c = copy.deepcopy(self.c)
        c.update(fma_mode='expanded612', active_fma_config=config)
        parts = report.route(self.text, self.c)
        text = parts['prior'] + parts['child'] + parts['cast'] + (out / 'first.el').read_text()
        return c, text

    def test_actual612_replaces108_not_duplicate(self):
        c, text = self.expanded_fixture()
        result = report.records(text, c)
        self.assertEqual(len(result['fma']), 612)
        self.assertEqual(result['retained']['prior']['original']['prior'][2], [])
        self.assertEqual(len(result['cast168']), 168)
        self.assertEqual(len(result['child15']), 798)
        with self.assertRaises(ValueError):
            report.records(text + self.c['legacy_fma_el'], c)

    def test_actual612_missing_direction_or_array_identity_rejected(self):
        c, text = self.expanded_fixture()
        lines = text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('Toggle 0to1 tentative_sign '))
        del lines[index]
        with self.assertRaises(ValueError):
            report.records('\n'.join(lines) + '\n', c)
        changed = text.replace('tentative_sign"', 'tentative_sign[0:0]"')
        with self.assertRaises(ValueError):
            report.records(changed, c)

    def test_duplicate_el_rejected(self):
        for directory in (report.CHILD, report.CAST):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                report.records(self.text + (directory / 'first.el').read_text(), self.c)

    def test_child_product_substitution_rejected(self):
        with self.assertRaises(ValueError):
            report.records(self.text.replace('compute_accumulator_updates', 'entry_occupancy'), self.c)

    def test_wrong_cast_checksum_rejected(self):
        with self.assertRaises(ValueError):
            report.records(self.text.replace('400336858', '400336859'), self.c)

    def test_missing_cast_whole_field_rejected(self):
        lines = self.text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith('Toggle mid_pipe_input_mant_q '):
                del lines[i]
                break
        with self.assertRaises(ValueError):
            report.records('\n'.join(lines) + '\n', self.c)

    def test_shared_scope_different_fields_allowed_duplicate_field_rejected(self):
        report.ownership(self.c)
        c = copy.deepcopy(self.c)
        c['child_config']['instances'][0]['signals'].append(c['child_config']['instances'][0]['signals'][0])
        with self.assertRaises(ValueError):
            report.ownership(c)

    def test_unqualified_fma_cannot_be_loaded(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                report.qualified_capture(Path(tmp), '0' * 64, 'EXACT_612_FMA_EXPANDED_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS')

    def test_host_output_cannot_run(self):
        with patch.object(report, 'check', return_value={'runtime_apply_authorized': False}), \
                patch.object(report.subprocess, 'Popen') as launch:
            with self.assertRaises(ValueError):
                report.run(Path('/not-used'), 'seal')
            launch.assert_not_called()

    def test_audit_missing_stage_schema_and_complement_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                report.audit_six(out, 'child', [[['path', 'meta', 'name']]])
            (out / 'child_before_0.tsv').write_text('handle\tpath\tmeta\tname\n1\tp\tm\tn\n')
            with self.assertRaises(ValueError):
                report.audit_six(out, 'child', [[['path', 'meta', 'name']]])

    def test_population_not_admitted_or_wrong_count_rejected(self):
        manifest = Path('/synthetic/formal/admission-manifest.json')
        book = dict(explicit_parent_authorized=True, output=str(manifest.parent),
                    input_pins={'/synthetic/source': '0' * 64},
                    output_pins={str(manifest.parent / name): '0' * 64
                                 for name in ('combined-bits.json', 'status.json')})
        for n, admitted in ((763, True), (761, False)):
            status = dict(aggregate_passed=n, coverage_admitted=admitted,
                          exact_prefix=True, full_OR_instances=6162)
            with self.subTest(n=n, admitted=admitted), patch.object(report.life, 'check'), \
                    patch.object(report.life, 'read_bound', side_effect=[book, {}, status]):
                with self.assertRaises(ValueError):
                    report.population(manifest, '0' * 64, self.c)

    def test_wrong_sealed_config_schema_rejected(self):
        c = dict(schema='foreign', output='/synthetic', population=761,
                 successor_entry=report.__file__, runtime_timeout_seconds=3600)
        with patch.object(report.life, 'read_bound', return_value=c):
            with self.assertRaises(ValueError):
                report.check(Path('/synthetic'), '0' * 64)

    def test_substantive_verifier_not_old_entry_wrapper(self):
        with patch.object(report, 'check', side_effect=ValueError('closed')):
            with self.assertRaisesRegex(ValueError, 'closed'):
                report.verify(Path('/unused'), 'seal')
        self.assertEqual(Path(report.frozen.prior.inherited.original_verify.__code__.co_filename).name,
                         'report_c910_combo742.py')

    def test_actual_generated_bracketed_scopes_full_five_stage_hook(self):
        from tempfile import TemporaryDirectory
        c, _ = self.expanded_fixture()
        c['child_references'] = []
        atom = report.frozen.prior.old.base.capture.tcl_atom
        selection = (report.BASE / 'selection.tcl').read_text() + '\nset child_instances {}\n'
        for index, instance in enumerate(c['child_config']['instances']):
            reference = report.table(report.CHILD / ('native_before_%d.tsv' % index),
                                    ['handle', 'path', 'meta', 'name', 'column1', 'column2'])
            c['child_references'].append(reference)
            selection += 'lappend child_instances [list %s [list %s]]\n' % (atom(instance['scope']),
                ' '.join(atom(s['native_label']) for s in instance['signals']))
        fma_out = report.life.OUT / 'fma_expanded_native_612-agent-20261007-04'
        for group in c['toggle_groups']:
            if group['policy'] == 'fma':
                group['reference'] = sorted(report.table(fma_out / ('native_initial_%d.tsv' % group['index']),
                                                        ['handle', 'path', 'meta', 'name']))
        cp = report.parser(report.HERE / 'capture_cast168_native_typed.py')
        for index in range(8):
            i = c['cast_config']['instances'][index]
            c['toggle_groups'].append(dict(scope=i['scope'], reference=report.normalized(
                cp.v2.inventory(report.CAST, c['cast_config'], 'before', index))))
        selection += 'set combo_groups {}\n'
        for index, group in enumerate(c['toggle_groups']):
            selection += 'lappend combo_groups [list %s %d [list %s]]\n' % (atom(group['scope']), index,
                ' '.join(atom(r[2]) for r in group['reference']))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'selection.tcl'
            path.write_text(selection)
            result = actual_hook_regression(path, c)
        self.assertEqual(result['stages'], list(report.STAGES))
        self.assertEqual(result['design_loads'], 1)
        self.assertFalse(result['EDA_launched'])


if __name__ == '__main__':
    unittest.main()
