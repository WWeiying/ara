import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import c910_srt_datapath_native as m


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = m.life.read_bound(m.REVIEW, m.REVIEW_SHA)
        cls.config = dict(instances=m.instances(cls.review))
        lines = []
        for instance in cls.config['instances']:
            lines += ['CHECKSUM: "%s %s"' % (instance['design_module_checksum'],
                                            instance['toggle_checksum']),
                      'INSTANCE: ' + instance['scope']]
            lines += ['Toggle %s "%s %s[%d:%d]"' % (s['name'], s['source_type'],
                       s['name'], s['left'], s['right']) for s in instance['signals']]
        cls.el = '\n'.join(lines) + '\n'

    def test_exact_full_1264(self):
        self.assertEqual(len(m.parse_el(self.el, self.config)), 1264)

    def test_logic_frontend_spelling(self):
        self.assertEqual(len(m.parse_el(self.el.replace('"reg ', '"logic ').replace(
            '"wire ', '"logic '), self.config)), 1264)

    def test_missing_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el('\n'.join(self.el.splitlines()[:-1]), self.config)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el + self.el.splitlines()[-1], self.config)

    def test_protected_control_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el + 'Toggle bound_sel "reg bound_sel[6:0]"', self.config)

    def test_slice_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el.replace('cur_rem[60:0]', 'cur_rem[59:0]', 1), self.config)

    def test_wrong_decl_type_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el.replace('"reg cur_rem', '"wire cur_rem', 1), self.config)

    def test_wrong_checksum_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el.replace('3969040510', '406590228', 1), self.config)

    def test_child_scope_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el.replace('x_ct_vfdsu_srt_radix16_with_sqrt\n',
                                      'x_ct_vfdsu_srt_radix16_with_sqrt.child\n', 1), self.config)

    def test_unknown_directive_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_el(self.el + 'Module recursive', self.config)

    def native_rows(self):
        instance = self.config['instances'][0]
        names = instance['protected'] + [s['name'] + '[%d:%d]' % (s['left'], s['right'])
                                       for s in instance['signals']]
        return ['handle\tpath\tmeta\tname'] + [
            '%d\t%s\t%s\t%s' % (i + 1, name, name, name) for i, name in enumerate(names)]

    def check_inventory(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'native_before_0.tsv').write_text('\n'.join(rows) + '\n')
            return m.inventory(out, self.config, 'before', 0)

    def test_full_protection_inventory(self):
        self.assertEqual(len(self.check_inventory(self.native_rows())), 210)

    def test_missing_protection_rejected(self):
        rows = self.native_rows()
        with self.assertRaises(ValueError):
            self.check_inventory(rows[:1] + rows[2:])

    def test_duplicate_native_token_rejected(self):
        rows = self.native_rows()
        with self.assertRaises(ValueError):
            self.check_inventory(rows + [rows[1]])

    def test_real_fma_procs_and_c910_binding(self):
        names = [line.split('\t')[-1] for line in self.native_rows()[1:]]
        instance = self.config['instances'][0]
        targets = [s['name'] + '[%d:%d]' % (s['left'], s['right']) for s in instance['signals']]
        with tempfile.TemporaryDirectory() as tmp:
            script = '\n'.join([
                'set ::c910_test_only 1',
                'set ::c910_fma_tcl {%s}' % (m.HERE / 'fma_datapath_native.tcl'),
                'source {%s}' % m.TCL, 'c910_primitives',
                'set ::env(DVE_COVERAGE_OUTPUT) {%s}' % tmp,
                'set ::fma_python unused', 'set ::fma_helper unused',
                'set ::names {%s}' % ' '.join(names),
                'proc gui_list_action {args} {}',
                'proc gui_covdetail_query {args} {return Toggle}',
                'proc gui_list_expand {args} {}', 'proc gui_process_events {args} {}',
                'proc exec {args} {return MOCK_INVENTORY_VALIDATED}',
                'proc gui_list_get {args} {',
                '  set key [lindex $args 2]; set item [lindex $args end]',
                '  if {$key eq "-firstChild"} {if {[llength $args] == 3} {return 1}; return 0}',
                '  if {$key eq "-nextSibling"} {if {$item < [llength $::names]} {return [expr {$item+1}]}; return 0}',
                '  return [lindex $::names [expr {$item-1}]]', '}',
                'set instance [list {%s} {%s} {%s} 0]' %
                (instance['scope'], ' '.join(targets), ' '.join(instance['protected'])),
                'if {[llength [c910_bind before $instance]] != 158} {error wrong_count}',
                'set ::names [lrange $::names 1 end]',
                'if {![catch {c910_bind selected $instance} failure]} {error accepted_missing_protection}',
                'if {[string first "Missing/duplicate" $failure] < 0} {error wrong_failure}',
                'puts REAL_PROCS_PASS'])
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('REAL_PROCS_PASS', result.stdout)
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
