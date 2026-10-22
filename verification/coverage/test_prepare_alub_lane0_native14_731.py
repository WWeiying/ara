"""Host fixtures test fail-closed policy; they are not actual native qualification."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest

import prepare_alub_lane0_native14_731 as subject


class Native14Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(subject.ARTIFACT.read_bytes())
        cls.config = dict(plan=cls.artifact['plan'], observed_branch_signatures=
                          subject.signatures(subject.NATIVE_FIXTURE.read_bytes()))

    def config_copy(self):
        return copy.deepcopy(self.config)

    def fixture(self):
        lines = []
        for scope, metrics in self.config['plan']['scopes'].items():
            for metric, rows in metrics.items():
                targets = [r for r in rows if r['target']]
                if not targets:
                    continue
                lines += ['CHECKSUM: "%s %s"' % (targets[0]['module_checksum'], targets[0]['metric_checksum']),
                          'INSTANCE: ' + scope]
                for row in targets:
                    point = row['point']
                    lines.append('ANNOTATION: "' + subject.ANNOTATION + '"')
                    if metric == 'line':
                        lines.append('Block %s "%s" "%s"' % (point['native_id'],
                            point['attributes']['chksum'], point['expression']))
                    else:
                        lines.append('Branch %s "%s" "%s" (%s) "%s"' % (point['native_id'],
                            point['attributes']['chksum'], point['expressions'][0]['exprstr'],
                            point['vector'], self.config['observed_branch_signatures'][point['vector']]))
        return ('\n'.join(lines) + '\n').encode('ascii')

    def reject(self, raw):
        with self.assertRaises((ValueError, UnicodeError)):
            subject.bind_native(raw, self.config)

    def test_sealed_static_artifact(self):
        self.assertEqual(subject.sha(subject.ARTIFACT), subject.ARTIFACT_SEAL)
        self.assertEqual(subject.population(self.config['plan']), {'line': 9, 'branch': 5})
        self.assertEqual(sum(len(r) for m in self.config['plan']['scopes'].values() for r in m.values()), 2224)

    def test_observed_native_fixture_pin(self):
        self.assertEqual(subject.sha(subject.NATIVE_FIXTURE), subject.NATIVE_FIXTURE_SHA)
        self.assertEqual(subject.sha(subject.HELP), subject.HELP_SHA)
        self.assertEqual(len(self.config['observed_branch_signatures']), 5)

    def test_host_exact14_format(self):
        self.assertEqual(len(subject.bind_native(self.fixture(), self.config)), 14)

    def test_block_point_checksum(self):
        self.reject(self.fixture().replace(b'Block 97 "3113095913"', b'Block 97 "1"', 1))

    def test_block_signature(self):
        self.reject(self.fixture().replace(b'if (SupportReduct)', b'if (SupportReduct_CHANGED)', 1))

    def test_branch_signature(self):
        self.reject(self.fixture().replace(b'cmd.conv OpQueueReductionZExt', b'cmd.conv OpQueueConversionNone', 1))

    def test_module_checksum(self):
        self.reject(self.fixture().replace(b'1532764271', b'1', 1))

    def test_metric_checksum(self):
        self.reject(self.fixture().replace(b'3998926456', b'1', 1))

    def test_spec_checksum(self):
        self.reject(self.fixture().replace(b'718333796', b'1', 1))

    def test_expression(self):
        self.reject(self.fixture().replace(b'"cmd.conv"', b'"cmd.eew"', 1))

    def test_protected_lane(self):
        self.reject(self.fixture().replace(b'gen_lanes[0]', b'gen_lanes[1]'))

    def test_alua_seed(self):
        self.reject(self.fixture().replace(b'i_operand_queue_alu_b', b'i_operand_queue_alu_a'))

    def test_no_broad_directive(self):
        self.reject(self.fixture() + b'INSTANCE: whole\n')
        self.reject(self.fixture() + b'Toggle 1\n')

    def test_duplicate(self):
        raw = self.fixture()
        self.reject(raw + raw)

    def test_missing(self):
        lines = self.fixture().splitlines(keepends=True)
        self.reject(b''.join(lines[:-2]))

    def test_raw_index_not_selector(self):
        self.reject(self.fixture().replace(b'Block 97 ', b'Block 99 ', 1))

    def test_nonascii(self):
        self.reject(self.fixture().replace(b'cmd.conv OpQueueReductionZExt', b'\xc8', 1))

    def test_target_drift(self):
        config = self.config_copy()
        first = next(iter(config['plan']['scopes'].values()))['line'][0]
        first['target'] = not first['target']
        with self.assertRaises(ValueError):
            subject.population(config['plan'])

    def audit_fixture(self, stage):
        rows = []
        for scope, metrics in self.config['plan']['scopes'].items():
            for metric, points in metrics.items():
                for point in points:
                    key = point['coordinate']
                    if metric == 'line':
                        meta, path = 'Block' + key, 'Block' + key
                    else:
                        sid, vid = key.split(',')
                        meta = 'Branch' + sid + '.' + vid
                        path = 'Item' + sid + '.' + meta
                    rows.append([scope, metric, key, meta, path,
                                 str(int(stage in ('selected', 'reloaded') and point['target']))])
        return rows

    def run_audit(self, rows, stage, previous=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'states.tsv'
            with path.open('w', newline='') as stream:
                writer = csv.writer(stream, delimiter='\t')
                writer.writerow(['scope', 'metric', 'coordinate', 'meta', 'path', 'excluded'])
                writer.writerows(rows)
            return subject.audit_states(path, self.config, stage, previous)

    def test_five_stage_full_protection(self):
        previous = None
        for stage in subject.native.STAGES:
            previous = self.run_audit(self.audit_fixture(stage), stage, previous)
            self.assertEqual(len(previous), 2224)

    def test_protected_leak(self):
        rows = self.audit_fixture('selected')
        next(r for r in rows if r[-1] == '0')[-1] = '1'
        with self.assertRaises(ValueError):
            self.run_audit(rows, 'selected')

    def test_missing_protection(self):
        with self.assertRaises(ValueError):
            self.run_audit(self.audit_fixture('before')[:-1], 'before')

    def test_native_meta_not_raw(self):
        rows = self.audit_fixture('before')
        rows[0][3] = 'Block9999'
        with self.assertRaises(ValueError):
            self.run_audit(rows, 'before')

    def test_reload_identity_drift(self):
        previous = self.run_audit(self.audit_fixture('before'), 'before')
        rows = self.audit_fixture('reloaded')
        rows[0][4] = 'Other.' + rows[0][4]
        with self.assertRaises(ValueError):
            self.run_audit(rows, 'reloaded', previous)


class TclHostFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tcl = tkinter.Tcl()
        self.tcl.eval('set dbg_library_only 1')
        self.tcl.call('source', str(subject.native.TCL))
        self.tcl.call('source', str(subject.ADAPTER))

    def test_empty_tokens_only(self):
        for raw in ('{}', '{} {}', ''):
            self.assertEqual(self.tcl.eval('alub14_selection line {' + raw + '}'), '')
        self.assertEqual(self.tcl.eval('alub14_selection line {{} Block97}'), 'Block97')
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('alub14_selection line {{ } Block97}')

    def test_duplicate_selection(self):
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('alub14_selection line {Block97 Block97}')

    def test_native_branch_selection(self):
        self.assertEqual(self.tcl.eval('alub14_selection branch {{} Branch5.28}'), 'Branch5.28')
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('alub14_selection branch {48}')

    def test_actual_singleton_readback(self):
        self.tcl.eval('''
            set actual {{}}
            proc gui_list_get_selected {args} {global actual; return $actual}
            proc gui_list_select {args} {
                global actual
                if {[lsearch -exact $args -select] >= 0} {set actual [lindex $args end]} else {set actual {}}
            }
            dbg_select line Block97
        ''')
        self.assertEqual(self.tcl.eval('set actual'), 'Block97')
        self.tcl.eval('proc gui_list_select {args} {global actual; set actual Block98}')
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('dbg_select line Block97')

    def test_session_no_reload_of_adapter(self):
        body = self.tcl.eval('info body dbg_session')
        self.assertNotIn('source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]', body)
        self.assertIn(subject.ANNOTATION, body)
        self.assertIn(' first --output ', body)
        self.assertLess(body.index('dbg_audit before'), body.index('eval gui_exclude_items'))
        self.assertLess(body.index(' first --output '), body.index('gui_exclusion_file -load'))

    def test_line_category_stays_hold(self):
        self.tcl.eval('''
            array set dbg_keys {scope|line {97}}
            proc gui_list_action {args} {}
            proc gui_covdetail_query {args} {return Line}
            proc gui_list_expand {args} {}
            proc gui_list_get {args} {
                if {[lsearch -exact $args -meta] >= 0} {return Block}
                if {[lsearch -exact $args -path] >= 0} {return Block}
                if {[lsearch -exact $args -nextSibling] >= 0} {return {}}
                return category
            }
        ''')
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('dbg_metadata scope line')

    def line_leaf_stub(self, child_count=0):
        self.tcl.eval('''
            array set dbg_keys {scope|line {97}}
            proc gui_list_action {args} {global drilled; if {[lsearch -exact $args Category]>=0} {set drilled 1}}
            proc gui_covdetail_query {args} {return Line}
            proc gui_list_expand {args} {}
            set drilled 0
            proc gui_list_get {args} {
                global drilled count
                if {[lsearch -exact $args -childCount]>=0} {return $count}
                if {[lsearch -exact $args -meta]>=0} {if {$drilled} {return Block97}; return Block}
                if {[lsearch -exact $args -path]>=0} {return Block97}
                if {[lsearch -exact $args -nextSibling]>=0} {return {}}
                if {[lindex $args end] eq "leaf"} {return {}}
                return leaf
            }
        ''')
        self.tcl.setvar('count', child_count)

    def test_category_to_actual_leaf(self):
        self.line_leaf_stub()
        result = self.tcl.eval('dbg_metadata scope line')
        self.assertEqual(self.tcl.splitlist(result)[0], '97')
        self.assertEqual(self.tcl.splitlist(self.tcl.splitlist(result)[1]), ('Block97', 'Block97'))

    def test_nonleaf_rejected(self):
        self.line_leaf_stub(1)
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('dbg_metadata scope line')

    def test_missing_actual_leaf_rejected(self):
        self.line_leaf_stub()
        self.tcl.eval('set dbg_keys(scope|line) {97 98}')
        with self.assertRaises(tkinter.TclError):
            self.tcl.eval('dbg_metadata scope line')


if __name__ == '__main__':
    unittest.main()
