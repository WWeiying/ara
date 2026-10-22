import copy
from pathlib import Path
import tempfile
import unittest

import verify_trusted_ip797_readonly as r


class SupplementalTests(unittest.TestCase):
    def setUp(self):
        self.root = 'ara_tb.dut.i_ara_soc.i_system.i_fma'
        self.outside = 'CHECKSUM: "4"\nINSTANCE: ara_tb.dut.i_ara_soc.i_system.i_control\nToggle ready "logic ready"\n'
        self.whole = 'CHECKSUM: "5"\nANNOTATION: "' + r.ANNOTATION + '"\nINSTANCE:' + self.root + '\n'
        self.config = dict(trusted_roots={self.root: '5'}, retained_EL_seal=r.s.semantic_seal(r.s.semantic(self.outside)),
                           output='/actual', tool_identity={'executable': '/dve'}, expected_cgroup='/unit')
        self.terminal = dict(returncode=0, timeout=False, config_seal='sealed',
                             actual_dve=[dict(pid=42, executable_verified=True, cwd='/actual', executable='/dve', cgroup='/unit')])
        self.gui = '\n'.join(r.MARKERS) + '\n'

    def test_real_native_whole_header_annotation_before_instance(self):
        r.whole_gate(self.whole + self.outside, self.config)

    def test_reordered_repeated_same_annotation_and_legacy_point(self):
        annotation = 'ANNOTATION: "' + r.ANNOTATION + '"\n'
        text = 'CHECKSUM: "5"\nINSTANCE:' + self.root + '\n' + annotation * 2
        legacy = 'CHECKSUM: "5 123"\nANNOTATION: "legacy untouched"\nINSTANCE:' + self.root + '\nToggle v [3:0] "logic v[3:0]"\n'
        r.whole_gate(text + legacy + self.outside, self.config)

    def test_missing_wrong_or_mixed_annotation_rejected(self):
        for text in (self.whole.replace('ANNOTATION: "' + r.ANNOTATION + '"\n', ''),
                     self.whole.replace(r.ANNOTATION, 'unreachable'),
                     self.whole + 'ANNOTATION: "wrong"\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                r.whole_gate(text + self.outside, self.config)

    def test_duplicate_wrong_checksum_and_multi_instance_rejected(self):
        for text in (self.whole * 2, self.whole.replace('"5"', '"6"'),
                     self.whole + 'INSTANCE:' + self.root + '\n'):
            with self.assertRaises(ValueError): r.whole_gate(text + self.outside, self.config)

    def test_missing_extra_descendant_parent_namespace_rejected(self):
        for text in ('', self.whole + self.whole.replace(self.root, self.root + '.child'),
                     self.whole + self.whole.replace(self.root, 'ara_tb.dut.i_ara_soc.i_system'),
                     self.whole.replace(self.root, self.root + '2')):
            with self.assertRaises(ValueError): r.whole_gate(text + self.outside, self.config)

    def test_outside_inherited_changes_rejected(self):
        with self.assertRaises(ValueError): r.whole_gate(self.whole, self.config)
        r.whole_gate(self.whole + self.outside.replace('INSTANCE:', 'ANNOTATION: "historical"\nINSTANCE:'), self.config)

    def test_terminal_exact_export_markers_pass(self):
        self.assertEqual(r.terminal_markers(self.terminal, self.config, 'sealed', self.gui, ''), dict.fromkeys(r.MARKERS, 1))

    def test_wrong_terminal_seal_rc_timeout_and_identity_rejected(self):
        for key, value in (('config_seal', 'other'), ('returncode', 1), ('returncode', False), ('timeout', True)):
            bad = copy.deepcopy(self.terminal); bad[key] = value
            with self.assertRaises(ValueError): r.terminal_markers(bad, self.config, 'sealed', self.gui, '')
        bad = copy.deepcopy(self.terminal); bad['actual_dve'][0]['cgroup'] = '/wrong'
        with self.assertRaises(ValueError): r.terminal_markers(bad, self.config, 'sealed', self.gui, '')

    def test_missing_duplicate_substring_markers_rejected(self):
        for marker in r.MARKERS:
            for gui in (self.gui.replace(marker + '\n', ''), self.gui + marker + '\n', self.gui.replace(marker, 'prefix ' + marker)):
                with self.assertRaises(ValueError): r.terminal_markers(self.terminal, self.config, 'sealed', gui, '')

    def test_export_failed_even_with_done_rejected(self):
        with self.assertRaises(ValueError):
            r.terminal_markers(self.terminal, self.config, 'sealed', self.gui + 'DVE_COVERAGE_EXPORT_FAILED: bad\n', '')

    def test_recursive_gui_logs_and_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            out = Path(directory); gui = out / 'DVEfiles'; gui.mkdir(); (gui / 'nested').mkdir()
            (gui / 'dve_gui.log').write_text(self.gui); (gui / 'nested/helper.log').write_text('native')
            self.assertEqual(len(r.gui_pins(out)), 2)
            (Path(external) / 'escape.log').write_text('foreign')
            (gui / 'escape.log').symlink_to(Path(external) / 'escape.log')
            with self.assertRaises(ValueError): r.gui_pins(out)

    def test_missing_actual_gui_log_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): r.gui_pins(Path(directory))


if __name__ == '__main__':
    unittest.main()
