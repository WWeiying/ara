import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_lzc_seven_foreground_recovery_v2 as subject


class ScopedIdentityTests(unittest.TestCase):
    def process(self, root, pid, argv, comm, cwd):
        entry = root / str(pid)
        entry.mkdir()
        (entry / 'cmdline').write_bytes(b'\0'.join(v.encode() for v in argv) + b'\0')
        (entry / 'comm').write_text(comm + '\n')
        (entry / 'status').write_text('State:\tS (sleeping)\n')
        (entry / 'cwd').symlink_to(cwd)
        return entry

    def test_real_sd_pam_identity_unreadable_cwd_not_eda(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            entry = self.process(Path(temporary), 624598, ['(sd-pam)'], '(sd-pam)', subject.OUTPUT)
            resolve = Path.resolve
            def checked(path, *args, **kwargs):
                if path == entry / 'cwd':
                    raise AssertionError('Unrelated PAM cwd must not be inspected')
                return resolve(path, *args, **kwargs)
            with patch.object(Path, 'resolve', checked):
                self.assertFalse(subject.inspect_candidate(entry))

    def test_potential_eda_unreadable_cwd_remains_hold(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            entry = self.process(root, 900001, ['/tools/dve.exe'], 'dve.exe', subject.OUTPUT)
            resolve = Path.resolve
            def checked(path, *args, **kwargs):
                if path == entry / 'cwd':
                    raise PermissionError('real environmental denial')
                return resolve(path, *args, **kwargs)
            with patch.object(Path, 'resolve', checked), self.assertRaisesRegex(ValueError, 'possible target'):
                subject.inspect_candidate(entry)

    def test_sd_pam_spoofed_command_and_unknown_identity_not_ignored(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            entry = self.process(root, 900001, ['/tools/dve.exe'], '(sd-pam)', subject.OUTPUT)
            self.assertTrue(subject.inspect_candidate(entry))
            (entry / 'cmdline').write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'empty command'):
                subject.inspect_candidate(entry)
            read = Path.read_bytes
            def denied(path):
                if path == entry / 'cmdline':
                    raise PermissionError('cmdline inaccessible')
                return read(path)
            with patch.object(Path, 'read_bytes', denied), self.assertRaisesRegex(ValueError, 'cannot classify'):
                subject.inspect_candidate(entry)

    def test_target_dve_worker_and_recovery_match_unrelated_dve_preserved(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            self.process(root, 900001, ['/tools/dve.exe', '-script', str(subject.original.generic.TCL)], 'dve.exe', subject.OUTPUT)
            self.process(root, 900002, ['/tools/dve.exe'], 'dve.exe', root)
            self.process(root, 900003, ['/usr/bin/python3', str(subject.original.SCRIPT), '_background-worker', '--output', str(subject.OUTPUT)], 'python3', root)
            self.process(root, 900004, ['/usr/bin/python3', str(subject.SCRIPT), '--sidecar', str(subject.SIDECAR)], 'python3', root)
            self.process(root, 900005, ['/bin/bash', '-c', 'exec /tools/dve.exe -cov'], 'bash', subject.OUTPUT)
            self.assertEqual(set(subject.scoped_candidates(root)), {900001, 900003, 900004, 900005})

    def test_scoped_guard_keeps_original_gate_and_target_hold(self):
        with patch.object(subject.prior, 'fast_guard', return_value=('original-launch', 'runtime')) as original, \
             patch.object(subject, 'scoped_candidates', return_value=[]):
            self.assertEqual(subject.fast_guard(), ('original-launch', 'runtime'))
            original.assert_called_once_with()
        with patch.object(subject.prior, 'fast_guard', return_value=(None, None)), \
             patch.object(subject, 'scoped_candidates', return_value=[3080799]), self.assertRaisesRegex(ValueError, 'Live target'):
            subject.fast_guard()

    def test_private_entry_same_receipt_no_frozen_mutation_no_spawn(self):
        self.assertIs(subject.run.__globals__['reviewed'], subject.reviewed)
        self.assertIs(subject.run.__globals__['original'], subject.original)
        self.assertEqual(subject.SIDECAR, subject.prior.SIDECAR)
        self.assertEqual(subject.OUTPUT, subject.prior.OUTPUT)
        self.assertIs(subject.prior.main.__globals__['fast_guard'], subject.prior.fast_guard)
        self.assertIn(str(Path(subject.prior.__file__)), [str(p) for p in subject.scoped_dependencies()])
        self.assertEqual(subject.frozen.sha(Path(subject.prior.__file__)), subject.PRIOR_SHA)
        self.assertIn('scoped_dependencies', subject.prepare.__code__.co_names)
        self.assertIn('scoped_dependencies', subject.reviewed.__code__.co_names)
        with self.assertRaisesRegex(ValueError, 'parent'):
            subject.run(subject.SIDECAR, 'not-reviewed', False)

    def test_preparation_pins_successor_and_frozen_base_without_launch(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            sidecar = Path(temporary) / 'mock-sidecar'
            with patch.object(subject, 'SIDECAR', sidecar), \
                 patch.object(subject, 'fast_guard', return_value=({'command': ['NO_EDA']}, None)):
                record = subject.prepare(sidecar)
                seal = subject.frozen.sha(sidecar / 'recovery-plan.json')
                self.assertEqual(subject.reviewed(sidecar, seal), record)
                self.assertTrue(all(record['pins'][str(p)] == subject.frozen.sha(p)
                                    for p in subject.scoped_dependencies()))
                self.assertFalse((sidecar / 'recovery-receipt.json').exists())

    def test_empty_command_only_verified_zombie_not_live_unknown_is_ignored(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            entry = self.process(Path(temporary), 160164, [], 'common_shell_ex', subject.OUTPUT)
            with self.assertRaisesRegex(ValueError, 'empty command'):
                subject.inspect_candidate(entry)
            (entry / 'status').write_text('Name:\tcommon_shell_ex\nState:\tZ (zombie)\n')
            self.assertFalse(subject.inspect_candidate(entry))


if __name__ == '__main__':
    unittest.main()
