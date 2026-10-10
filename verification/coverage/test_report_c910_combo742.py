import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import report_c910_combo742 as report


class ComboTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((report.PRIOR / 'config.json').read_bytes())
        cls.config['c910_config'] = json.loads((report.C910 / 'config.json').read_bytes())
        cls.text = (report.PRIOR / 'applied.el').read_text() + (report.C910 / 'first.el').read_text()

    def test_actual_qualified_union(self):
        r = report.records(self.text, self.config)
        self.assertEqual([len(x) for x in r['prior']], [124, 4, 108])
        self.assertEqual(len(r['c910']), 1264)
        self.assertEqual(r['dwc'], [])

    def test_actual_dwc_first_typed_union_with_directional_scalars(self):
        dwc = report.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-03'
        c = dict(self.config, dwc_config=json.loads((dwc / 'config.json').read_bytes()),
                 dwc_parser=dict(path=str(report.HERE / 'qualify_dwc_points742_v2.py'),
                                 sha256=report.life.digest(report.HERE / 'qualify_dwc_points742_v2.py')))
        first = (report.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-01/first.el').read_text()
        combined = report.records(self.text + first, c)
        self.assertEqual(sum(r[0] == 'fsm' for r in combined['dwc']), 31)
        self.assertEqual(sum(r[0] == 'tgl' for r in combined['dwc']), 168)
        with self.assertRaises(ValueError):
            report.records(self.text + first.replace('Toggle 0to1 ', 'Toggle 1to0 '), c)

    def test_c910_missing_duplicate_protected_checksum_rejected(self):
        c = (report.C910 / 'first.el').read_text()
        lines = c.splitlines()
        prior = (report.PRIOR / 'applied.el').read_text()
        for wrong in ('\n'.join(lines[:-1]), c + '\n' + lines[-1],
                      c + '\nToggle bound_sel "net bound_sel[6:0]"\n',
                      c.replace('3969040510', '0')):
            with self.assertRaises(ValueError):
                report.records(prior + wrong, self.config)

    def test_foreign_or_mixed_scope_rejected(self):
        for wrong in (self.text.replace('.gen_lanes[0].', '.gen_lanes[9].'),
                      'INSTANCE: unbound\n' + self.text,
                      self.text + '\nINSTANCE: injected\n'):
            with self.assertRaises(ValueError):
                report.records(wrong, self.config)

    def test_native_complete_complement_header_and_duplicates(self):
        actual = report.native_tree(report.C910 / 'native_before_0.tsv')
        self.assertEqual(len(actual), 210)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'tree.tsv'
            path.write_text('wrong\n')
            with self.assertRaises(ValueError):
                report.native_tree(path)
            path.write_text('handle\tpath\tmeta\tname\n1\tx\tx\tx\n2\tx\tx\tx\n')
            with self.assertRaises(ValueError):
                report.native_tree(path)

    def test_private_runner_changes_only_hook_environment(self):
        original = report.base.subprocess.Popen
        captured = {}

        def function(code, namespace):
            captured.update(namespace)
            return lambda out, seal: None

        with patch.object(report, 'FunctionType', function):
            report.run(Path('/unused'), 'seal')
        env = dict(DVE_REVIEWED_WAIVERS='old', OTHER='preserved')
        with patch.object(report.base.subprocess, 'Popen') as popen:
            captured['subprocess'].Popen(['command'], env=env, cwd='/cwd')
            self.assertEqual(popen.call_args.kwargs['env'],
                             dict(DVE_REVIEWED_WAIVERS=str(report.TCL), OTHER='preserved'))
            self.assertEqual(env['DVE_REVIEWED_WAIVERS'], 'old')
        self.assertIs(report.base.subprocess.Popen, original)

    def test_real_hook_five_stages_and_recalculation_before_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'selection.tcl').write_text('set fx_groups {}\nset combo_groups {}\nset combo_has_dwc 0\n')
            (out / 'live-ready').touch()
            script = 'source {%s}\nset ::env(DVE_COVERAGE_OUTPUT) {%s}\n' % (report.TCL, out)
            script += r'''
set ::calls {}
proc p740_save {name} {lappend ::calls save_$name}
proc fx_audit {stage active} {lappend ::calls fsm_$stage}
proc combo_inventory {stage} {lappend ::calls tgl_$stage}
proc p740_summary {stage} {lappend ::calls summary_$stage}
proc gui_exclusion_file {args} {lappend ::calls load}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion {args} {lappend ::calls [lindex $args end]}
proc gui_process_events {args} {}
apply_reviewed_waivers CoverageTable.1
puts $::calls
'''
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.stderr, '')
            self.assertIn('COMBO742_NATIVE_DONE', result.stdout)
            self.assertIn('load -recalculate fsm_applied tgl_selected save_applied.el', result.stdout)
            self.assertIn('-reset -recalculate fsm_reset tgl_reset save_reset-empty.el', result.stdout)
            self.assertIn('summary_final -reset -recalculate save_cleanup-empty.el', result.stdout)


if __name__ == '__main__':
    unittest.main()
