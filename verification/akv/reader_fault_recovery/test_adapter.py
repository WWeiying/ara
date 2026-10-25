"""Host-only command-envelope mutations; no simulator or evidence rewriting."""
import importlib.util
from pathlib import Path
import shlex
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter as a

spec = importlib.util.spec_from_file_location(
    'recovery_original_gate_tests', HERE.parent / 'reader_fault_gate/test_gate.py')
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.GateTests.setUpClass()
        cls.rtl = fixtures.GateTests.rtl

    def setUp(self):
        self.target = fixtures.TARGET
        self.argv = ['/reviewed/baseline/simv', '-no_save', '-ucli', '-do',
                     '/reviewed/probe.tcl', '-l', '/reviewed/run.vcs.log',
                     '+PRELOAD=/reviewed/program.elf',
                     f'+READER_FAULT_TARGET={self.target:x}', '+QBS_PERF', '+AKV_PERF']
        self.body = fixtures.GateTests().transcript()
        self.text = 'Command: ' + shlex.join(self.argv) + '\n' + self.body

    def test_exact_header_and_full_program_contract(self):
        self.assertEqual(a.command_body(self.text, self.target, self.argv), self.body)
        self.assertEqual(a.check_log(self.text, self.rtl, self.target, self.argv)['commands'], 71)
        # The failure in the old parser remains reproducible, not silently fixed.
        with self.assertRaisesRegex(ValueError, 'Unknown/malformed injection record'):
            a.c.check.check_log(self.text, self.rtl, self.target)

    def test_missing_duplicate_late_and_malformed_headers(self):
        header = self.text.split('\n', 1)[0]
        for text in (self.body, '\n' + self.text, self.text + '\n' + header,
                     self.text.replace('Command: ', 'Command:', 1),
                     header + '\\\n' + self.body, header + '\r\n' + self.body,
                     header + '\x00\n' + self.body, header):
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                a.command_body(text, self.target, self.argv)

    def test_wrong_image_elf_profile_log_target_or_flags(self):
        for old, new in (('/baseline/simv', '/candidate/simv'),
                         ('program.elf', 'different.elf'), ('probe.tcl', 'different.tcl'),
                         ('run.vcs.log', 'different.log'), ('+QBS_PERF', '+UNVERIFIED'),
                         (f'TARGET={self.target:x}', f'TARGET={self.target+64:x}')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                a.command_body(self.text.replace(old, new, 1), self.target, self.argv)

    def test_bad_expected_argv_and_duplicate_target_reject(self):
        for argv in ([], self.argv + [f'+READER_FAULT_TARGET={self.target:x}'],
                     self.argv + ['+READER_FAULT_TARGET=0'], ['not-simv', *self.argv[1:]]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                a.command_body(self.text, self.target, argv)
        with self.assertRaises(ValueError):
            a.command_body(self.text, True, self.argv)

    def test_runtime_failures_are_not_removed(self):
        for suffix in ('\nREADER_FAULT_UNKNOWN x=0', '\nREADER_FAULT_ERROR bad',
                       '\nFAIL hidden=1', '\nUVM_ERROR : 1', '\n' + a.c.check.INJECTOR):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                a.check_log(self.text + suffix, self.rtl, self.target, self.argv)

    def test_missing_metric_or_software_result_reject(self):
        for prefix in ('[QBS_PERF] ', 'READER_DRAIN_'):
            lines = self.text.splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith(prefix))
            del lines[index]
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                a.check_log('\n'.join(lines), self.rtl, self.target, self.argv)


if __name__ == '__main__':
    unittest.main()
