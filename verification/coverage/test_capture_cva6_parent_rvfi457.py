"""Actual entry/source/eval five-stage regression and exact typed negatives."""
import ast
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import capture_cva6_parent_rvfi457 as m


class ExactParent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = m.life.read_bound(m.REVIEW, m.REVIEW_SHA)
        cls.c = dict(source_review_sha256=m.REVIEW_SHA, bindings=m.bindings(cls.r),
                     scope=cls.r['scope'], design_checksum=cls.r['design_checksum'],
                     toggle_checksum=cls.r['toggle_checksum'], pins={str(m.REVIEW): m.REVIEW_SHA},
                     design='frozen-design', sample='one-vdb', test='one-test',
                     python=sys.executable, helper=str(Path(m.__file__).resolve()))

    def directives(self, pairs=True):
        lines = ['CHECKSUM: "%s %s"' % (self.c['design_checksum'], self.c['toggle_checksum']),
                 'INSTANCE: ' + self.c['scope'], 'ANNOTATION: "' + m.ANNOTATION + '"']
        for p in self.c['bindings']:
            if p['role'] != 'target': continue
            if pairs and p['width'] == 1:
                bit = ' [0]' if p['kind'] == 'vectornode' else ''
                lines.extend('Toggle ' + d + ' ' + p['name'] + bit + ' "logic ' + p['label'] + '"'
                             for d in ('0to1', '1to0'))
            else:
                lines.append('Toggle ' + p['name'] + ' "logic ' + p['label'] + '"')
        return '\n'.join(lines) + '\n'

    def execute(self, out, mutation='', broken_selection=False):
        (out / 'DVEfiles').mkdir()
        m.life.save(out / 'config.json', self.c)
        plain = m.selection(self.c)
        (out / 'selection.tcl').write_text(json.dumps(plain) if broken_selection else plain)
        # Reuse the already-tested real GUI boundary stubs read-only, not extracted production procs.
        tree = ast.parse((m.HERE / 'test_capture_system_rvfi788_v2.py').read_text())
        constants = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        original = [s for s in constants if 'proc gui_open_cov {args}' in s and 'proc mock_label {}' in s]
        self.assertEqual(len(original), 1)
        mock = original[0].replace('rvfi_', 'cr_').replace('!=788', '!=457')
        # Targets intentionally do not exist until actual-before binding succeeds.
        old = ' || [llength $::cr_targets]!=457'
        self.assertEqual(mock.count(old), 1); mock = mock.replace(old, '')
        self.assertEqual(mock.count('return path$item'), 1)
        mock = mock.replace('return path$item', 'return [lindex $::mock_labels [expr {$item-1}]]')
        old = '''    if {![regexp {^path([0-9]+)$} $token all index]} {error "Bad singleton token"}
    return [lindex $::mock_labels [expr {$index-1}]]'''
        self.assertEqual(mock.count(old), 1)
        mock = mock.replace(old, '''    if {[lsearch -exact $::mock_labels $token]<0} {error "Foreign singleton token"}
    return $token''')
        # Save the exact typed full457 serialization, including both scalar directions.
        old = 'foreach name $::mock_active {puts $f [lindex $::mock_directives [lsearch -exact $::cr_targets $name]]}'
        self.assertEqual(mock.count(old), 1)
        mock = mock.replace(old, 'puts -nonewline $f $::mock_native')
        self.assertEqual(mock.count('puts $f $::mock_header'), 1)
        mock = mock.replace('puts $f $::mock_header', '')
        labels = [p['allowed_labels'][-1] for p in self.c['bindings']]
        setup = 'set ::env(DVE_COVERAGE_OUTPUT) ' + m.atom(out) + '\n'
        setup += 'set ::env(CVA6_PARENT_RVFI457_SEAL) ' + m.atom(m.life.digest(out / 'config.json')) + '\n'
        setup += 'set mock_labels [list ' + ' '.join(m.atom(p) for p in labels) + ']\n'
        setup += 'set mock_native ' + '{' + self.directives() + '}\n'
        setup += 'set mock_header {};set mock_selection {};set mock_active {};set mock_action {};set mock_bad_reload 0;set mock_bad_empty 0\n'
        body = setup + mock + mutation + '\nproc boot {} {eval [read [set f [open ' + m.atom(m.ENTRY) + ' r]]]; close $f}\nboot\n'
        body += 'set f [open [file join $env(DVE_COVERAGE_OUTPUT) csv-probe.csv] w]\ncsv_row $f [list {a,b} {x"y} plain]\nclose $f\n'
        result = subprocess.run(['tclsh'], input='if {[catch {\n' + body + '\n} why]} {puts stderr "$why\n$::errorInfo";exit 1}\n',
                                text=True, capture_output=True, timeout=180)
        return result

    def test_frozen_source_pins_and_static(self):
        m.life.check(self.r['pins']); m.static(); m.contract(self.c)
        self.assertEqual(sum(p['kind'] == 'arrays' for p in self.c['bindings']), 31)
        self.assertEqual(sum(p['role'] == 'protected' for p in self.c['bindings']), 1315)

    def test_actual_entry_plain_selection_eval_five_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = self.execute(out)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('CVA6_PARENT_RVFI457_NATIVE_DONE', p.stdout)
            self.assertNotIn('CVA6_PARENT_RVFI457_FAILED', p.stdout)
            before = m.inventory(out, self.c, 'before')
            for stage in m.STAGES[1:]: self.assertEqual(m.inventory(out, self.c, stage), before)
            self.assertEqual(m.records((out / 'first.el').read_text(), self.c),
                             m.records((out / 'second.el').read_text(), self.c))
            for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
                self.assertEqual((out / name).read_bytes(), b'')
            with (out / 'csv-probe.csv').open() as stream:
                self.assertEqual(next(csv.reader(stream)), ['a,b', 'x"y', 'plain'])

    def test_json_selection_reproduction_rejected_before_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = self.execute(out, broken_selection=True)
            self.assertIn('CVA6_PARENT_RVFI457_FAILED', p.stdout)
            self.assertFalse((out / 'first.el').exists())
            self.assertEqual((out / 'cleanup-empty.el').read_bytes(), b'')

    def test_native_missing_array_rejected_before_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = self.execute(out, 'lset mock_labels end foreign_array')
            self.assertIn('Foreign/duplicate full compiled object', p.stdout)
            self.assertFalse((out / 'first.el').exists())
            self.assertEqual((out / 'cleanup-empty.el').read_bytes(), b'')

    def test_partial_reload_rejected_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = self.execute(out, 'set mock_bad_reload 1')
            self.assertIn('Target/protected exclusion differs', p.stdout)
            self.assertNotIn('CVA6_PARENT_RVFI457_NATIVE_DONE', p.stdout)
            self.assertEqual((out / 'cleanup-empty.el').read_bytes(), b'')

    def test_whole_or_exact_directional_equivalence(self):
        self.assertEqual(len(m.records(self.directives(), self.c)), 457)
        self.assertEqual(m.records(self.directives(), self.c), m.records(self.directives(False), self.c))

    def test_preserved_actual_typed457_serialization(self):
        self.assertEqual(m.precedent_records(self.c), m.records(self.directives(), self.c))

    def test_all_configuration_globals_reachable_or_rejected(self):
        for key in ('design', 'sample', 'test', 'scope', 'python', 'helper'):
            plain = m.selection(self.c)
            self.assertIn('set ::cr_' + key + ' ', plain)
        self.assertFalse(plain.startswith('"'))
        self.assertNotIn('\\n', plain)

    def test_protected_array_exclusion_cannot_pass_any_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); p = self.execute(out)
            self.assertIn('CVA6_PARENT_RVFI457_NATIVE_DONE', p.stdout)
            guard = next(p for p in self.c['bindings'] if p['kind'] == 'arrays')
            for stage in m.STAGES:
                path = out / ('native_' + stage + '.tsv')
                original = path.read_bytes()
                with path.open(newline='') as stream: rows = list(csv.DictReader(stream, delimiter='\t'))
                for row in rows:
                    if row['name'] in guard['allowed_labels']: row['excluded'] = '1'
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=['handle', 'path', 'meta', 'name', 'excluded'], delimiter='\t')
                    writer.writeheader(); writer.writerows(rows)
                with self.assertRaises(ValueError): m.inventory(out, self.c, stage)
                path.write_bytes(original)

    def test_pairs_qualifiers_ranges_scope_complement_negatives(self):
        text = self.directives(); directional = next(s for s in text.splitlines() if s.startswith('Toggle 0to1 '))
        vector = next(p for p in self.c['bindings'] if p['role'] == 'target' and p['width'] > 1)
        scalar = next(p for p in self.c['bindings'] if p['role'] == 'target' and p['width'] == 1)
        mutations = [text.replace(directional + '\n', '', 1), text + directional + '\n',
                     text + 'Toggle ' + scalar['name'] + ' "logic ' + scalar['label'] + '"\n',
                     text.replace('"logic ', '"wire ', 1),
                     text.replace(vector['label'], vector['name'] + '[1:0]', 1),
                     text.replace(self.c['scope'], self.c['scope'] + '.i_cva6_rvfi_probes', 1),
                     text.replace(self.c['toggle_checksum'], '1', 1),
                     text + 'Toggle clk_i "logic clk_i"\n',
                     text.replace(m.ANNOTATION, 'foreign', 1),
                     text.replace('Toggle ' + vector['name'], 'Toggle 0to1 ' + vector['name'], 1)]
        for changed in mutations:
            with self.subTest(change=changed[-100:]), self.assertRaises(ValueError): m.records(changed, self.c)

    def test_same_width_binding_shift_and_output_port_exception_not_generic(self):
        for key, value in (('portnode', '0'), ('left', '3')):
            c = copy.deepcopy(self.c); c['bindings'][0]['attributes'][key] = value
            with self.assertRaises(ValueError): m.contract(c)


if __name__ == '__main__': unittest.main()
