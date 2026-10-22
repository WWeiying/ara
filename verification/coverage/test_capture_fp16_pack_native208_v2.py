import copy
import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_fp16_pack_native208_v2 as c


class NativeFP16PackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved = c.load_inventory()
        selected = json.loads((c.reference.SEALED / 'capture-plan.json').read_bytes())
        cls.config = dict(targets=208, plan=c.make_plan(saved, selected, {}))

    def native(self, config=None):
        config = config or self.config
        lines = []
        for scope, metrics in config['plan']['scopes'].items():
            targets = [r for r in metrics['branch'] if r['target']]
            if not targets:
                continue
            lines += ['CHECKSUM: "%s %s"' % (targets[0]['module_checksum'], targets[0]['metric_checksum']), 'INSTANCE: ' + scope]
            for r in targets:
                p = r['point']
                serialized = c.native_serialization(r)
                lines += ['ANNOTATION: "' + c.ANNOTATION + '"',
                    'Branch %s "%s" "%s" (%s) "%s"' % (p['native_id'], p['attributes']['chksum'],
                        serialized['expression'], p['vector'], serialized['signature'])]
        return ('\n'.join(lines) + '\n').encode()

    def test_exact208_complete_signatures(self):
        self.assertEqual(len(c.bind_native(self.native(), self.config)), 208)

    def test_signature_checksum_annotation_and_expression_drift(self):
        raw = self.native()
        for old, new in ((b"13'h1fcd ", b"13'h0000 "), (b'1926128194', b'0'),
                         (b'839910393', b'0'), (b'vfdsu_ex4_expnt_rst[12:0]', b'wrong'),
                         (c.ANNOTATION.encode(), b'other note')):
            self.assertIn(old, raw)
            with self.subTest(old=old), self.assertRaises(ValueError):
                c.bind_native(raw.replace(old, new, 1), self.config)

    def test_missing_duplicate_and_extra_records(self):
        raw = self.native().decode()
        lines = raw.splitlines()
        for changed in ('\n'.join(lines[:-2])+'\n', raw+lines[-2]+'\n'+lines[-1]+'\n', raw+'INSTANCE: ara_tb\n'):
            with self.subTest(), self.assertRaises(ValueError):
                c.bind_native(changed.encode(), self.config)

    def test_default_and_hit_targets_rejected(self):
        for field, value in (('hit', True), ('case_item', dict(name='default'))):
            bad = copy.deepcopy(self.config)
            row = next(r for metrics in bad['plan']['scopes'].values() for r in metrics['branch'] if r['target'])
            row[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                c.bind_native(self.native(), bad)

    def test_foreign_scope_not_allowed(self):
        bad = copy.deepcopy(self.config)
        scope = next(iter(bad['plan']['scopes']))
        bad['plan']['scopes'][scope.rsplit('.', 1)[0]+'.x_ct_vfdsu_round'] = bad['plan']['scopes'].pop(scope)
        with self.assertRaises(ValueError):
            c.bind_native(self.native(), bad)

    def test_actual_failed_first_exact208_offline(self):
        records = c.bind_native((c.OBSERVATION / 'first.el').read_bytes(), self.config)
        self.assertEqual(len(records), 208)
        self.assertFalse(c.load_serialization_observation()['native_roundtrip_qualified'])

    def test_inactive_default_suffix_strict(self):
        raw = self.native()
        self.assertIn(b',-', raw)
        for suffix in (b',0', b',1', b',--', b'', b',?'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                c.bind_native(raw.replace(b',-', suffix, 1), self.config)

    def test_default_subtree_structure_rejected(self):
        bad = copy.deepcopy(self.config)
        row = next(r for metrics in bad['plan']['scopes'].values() for r in metrics['branch'] if r['target'])
        row['point']['expressions'][1]['parent_bit'] = '53'
        with self.assertRaises(ValueError):
            c.bind_native(self.native(), bad)

    def test_boundary_target_rejected(self):
        bad = copy.deepcopy(self.config)
        row = next(r for metrics in bad['plan']['scopes'].values() for r in metrics['branch'] if r['point']['raw_index'] == 56)
        row['target'] = True
        with self.assertRaises(ValueError):
            c.validate_plan(bad['plan'])

    def context(self, mutation=None):
        literal = c.lifecycle.literal
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root/'sample.vdb/snps/coverage/db/testdata/one').mkdir(parents=True)
            (root/'live-ready').touch()
            plan = dict(self.config['plan'], design_vdb='/not-loaded/design.vdb', selected_test_vdb=str(root/'sample.vdb'))
            (root/'selection.tcl').write_text(c.common.selection(plan) +
                'set exp_python {/usr/bin/python3}\nset exp_driver {/not-run/driver.py}\n' +
                'set exp_test_identity {' + str(root/'sample/one') + '}\n')
            tree = []
            victim = None
            for scope, metrics in plan['scopes'].items():
                parents = {}
                for row in metrics['branch']:
                    sid, vid = row['coordinate'].split(',')
                    parents.setdefault(sid, []).append((vid, row))
                handles = ['P'+sid for sid in sorted(parents, key=int)]
                entries = [('ROOT,firstChild', handles[0])]
                for i, parent in enumerate(handles):
                    sid = parent[1:]
                    children = ['L'+sid+'_'+vid for vid, _ in parents[sid]]
                    entries += [(parent+',path', 'Item'+sid), (parent+',firstChild', children[0]),
                                (parent+',nextSibling', handles[i+1] if i+1<len(handles) else '0')]
                    for j, (vid, row) in enumerate(parents[sid]):
                        meta = 'Branch'+sid+'.'+vid
                        if row['decision'] == 'PROTECTED_DEFAULT':
                            meta = 'MISSING_DEFAULT'+sid+'.'+vid
                            victim = victim or (scope, meta)
                        entries += [(children[j]+',meta', meta), (children[j]+',path', 'Item'+sid+'.'+meta),
                                    (children[j]+',childCount', '0'),
                                    (children[j]+',nextSibling', children[j+1] if j+1<len(children) else '0')]
                for key, value in entries:
                    tree.append('set ' + literal('node(' + scope+'|'+key + ')') + ' ' + literal(value))
            script = '''set pack208_library_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
proc help args {return OK}
proc gui_open_cov args {error GATE_REACHED_NOT_EDA}
proc gui_list_action args {
    global current_scope
    set current_scope [lindex $args end]
}
proc gui_covdetail_query args {return Branch}
proc gui_list_expand args {}
proc gui_list_get args {
    global node current_scope
    set option [string range [lindex $args 2] 1 end]
    set item [lindex $args 3]
    if {$item eq ""} {set item ROOT}
    return $node($current_scope|$item,$option)
}
proc gui_list_get_selected args {global selected; return $selected}
proc gui_list_select args {
    global selected
    if {[lindex $args 4] eq "-unselect"} {set selected {}; return}
    set selected [lindex $args 5]
}
proc gui_exclusion args {
    global current_scope selected dbg_targets wrong_default
    if {[lindex $args end] ne "-selected"} {error COUNT_QUERY_FORBIDDEN}
    if {$current_scope eq [lindex $wrong_default 0] && $selected eq [lindex $wrong_default 1]} {return 1}
    if {![regexp {^(Branch|MISSING_DEFAULT|MISSING_ELSE)([0-9]+)\.([0-9]+)$} $selected unused kind sid vid]} {error NOT_SINGLETON}
    return [expr {[lsearch -exact $dbg_targets($current_scope|branch) "$sid,$vid"] >= 0}]
}
set selected {}
set wrong_default {}
%s
set failed [catch {pack208_session} message]
if {!$failed || $message ne "GATE_REACHED_NOT_EDA"} {error "SESSION_CONTEXT $message"}
%s
pack208_audit selected 1
puts CONTEXT_1144_PASS
''' % (c.HOOK, root, '\n'.join(tree),
                'set dbg_keys([lindex $dbg_scopes 0]|branch) {0,0}' if mutation=='inventory' else
                ('set wrong_default {'+literal(victim[0])+' '+literal(victim[1])+'}' if mutation=='default' else ''))
            script = 'if {[catch {\n'+script+'\n} detail]} {puts stderr $detail; exit 1}\n'
            fixture = root/'fixture.tcl'
            fixture.write_text(script)
            result = subprocess.run([shutil.which('tclsh'), str(fixture)], text=True, cwd=root, capture_output=True, timeout=30)
            rows = []
            if (root/'states_selected.tsv').exists():
                with (root/'states_selected.tsv').open() as stream:
                    rows = list(csv.DictReader(stream, delimiter='\t'))
                if result.returncode == 0:
                    c.audit_states(root/'states_selected.tsv', self.config, 'selected')
            return result, rows

    def test_real_Tcl_context_and_singleton1144_audit(self):
        result, rows = self.context()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONTEXT_1144_PASS', result.stdout)
        self.assertEqual(len(rows), 1144)
        self.assertEqual(sum(r['excluded']=='1' for r in rows), 208)
        self.assertEqual(sum(r['excluded']=='0' for r in rows), 936)

    def test_real_Tcl_inventory_and_default_mutations_rejected(self):
        for mutation, message in (('inventory', 'complete native/compiled selector inventory differs'),
                                  ('default', 'singleton differs')):
            result, _ = self.context(mutation)
            with self.subTest(mutation=mutation):
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('CONTEXT_1144_PASS', result.stdout)
                self.assertIn(message, result.stderr)


if __name__ == '__main__':
    unittest.main()


