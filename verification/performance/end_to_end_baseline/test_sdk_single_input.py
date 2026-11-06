"""Safety-contract tests for the host-only SDK differential consumer."""
import json
from pathlib import Path
import tempfile
import unittest

import prepare_sdk_single_input as target


class PreparationTests(unittest.TestCase):
    def test_all_public_functions_and_reject_data(self):
        self.assertEqual(target.public_symbols('qbs_z T 0 1\nqbs_a W 2 3\nprivate t 4 5\n'),
                         ['qbs_a', 'qbs_z'])
        for text in ('', 'qbs_data B 0 4', 'qbs_a T 0 1\nqbs_a T 0 1', 'qbs_bad-name T 0 1'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                target.public_symbols(text)

    def test_attempts_preserve_first_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = target.new_attempt(tmp)
            evidence = first / 'result.json'
            target.write(evidence, {'state': 'FAIL', 'error': 'original'})
            before = target.digest(evidence)
            second = target.new_attempt(tmp)
            self.assertNotEqual(first, second)
            self.assertEqual(before, target.digest(evidence))
            self.assertEqual(json.loads(evidence.read_text())['error'], 'original')

    def test_identity_gate_and_late_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'source.c'
            p.write_text('sealed')
            r = target.Run(Path(tmp))
            r.pin(p, target.digest(p))
            with self.assertRaises(ValueError):
                r.pin(p, '0' * 64)
            p.write_text('drift')
            with self.assertRaises(ValueError):
                r.verify()
            with self.assertRaises(ValueError):
                r.pin(p)

    def test_dependencies_include_system_headers_and_escaped_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a file.h', Path(tmp) / 'system.h'
            a.touch(); b.touch()
            escaped = str(a).replace(' ', '\\ ')
            self.assertEqual(target.dependency_paths(f'o: {escaped} \\\n {b}\n'), [a, b])
            for text in ('', 'o:\n', f'o: {b}\nsecond: {b}\n'):
                with self.assertRaises(ValueError):
                    target.dependency_paths(text)

    def test_failed_command_record_and_first_stdout_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = target.Run(Path(tmp))
            with self.assertRaises(ValueError):
                r.command(['/usr/bin/false'])
            evidence = Path(tmp) / 'commands.json'
            self.assertEqual(json.loads(evidence.read_text())[0]['returncode'], 1)
            self.assertTrue(Path(r.commands[0]['log']).exists())

    def test_fixed_paths_and_fixture_contract(self):
        self.assertEqual(target.MAIN, Path('/home/wangwy/openproject/ara_dsa'))
        self.assertEqual(len(target.FIXTURES), 7)
        self.assertEqual(target.SUCCESS, 'SDK_SINGLE_INPUT_HOST_DIFF_PASS')
        self.assertEqual(target.FIXTURES[-1], 'tests/qbs_context_cost_test.c')
        with self.assertRaises(ValueError):
            target.main(['--output', '/tmp/not-assigned'])


if __name__ == '__main__':
    unittest.main()
