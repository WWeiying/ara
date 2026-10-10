"""No EDA: archive selection and terminal evidence failure tests."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_units as runner


class RunnerTests(unittest.TestCase):
    def invoke(self, args=(), output='VLDU_SUITE_PASS\n', compile_exit=0,
               run_exit=0, archive=None, mutate_image=False):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'new'
            calls = []

            def execute(command, **kwargs):
                calls.append(command)
                if command[0] == 'vcs':
                    (directory / 'simv').write_bytes(b'unit-test-image-not-executable')
                    return SimpleNamespace(returncode=compile_exit)
                kwargs['stdout'].write(output)
                if mutate_image:
                    (directory / 'simv').write_bytes(b'changed')
                return SimpleNamespace(returncode=run_exit)

            with patch.object(runner, 'ARCHIVE', archive or Path(tmp) / 'absent.tgz'), \
                    patch.object(runner.subprocess, 'run', side_effect=execute), \
                    patch('sys.argv', ['run_units', '--suite', 'vldu', '--output', str(directory), *args]), \
                    contextlib.redirect_stdout(io.StringIO()):
                rc = runner.main()
            return rc, json.loads((directory / 'status.json').read_text()), calls

    def test_candidate_no_archive_required(self):
        rc, status, calls = self.invoke()
        self.assertEqual(rc, 0)
        self.assertNotIn('archive_sha256', status)
        self.assertEqual(len(calls), 2)

    def test_explicit_baseline_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'fixture.tgz'
            with tarfile.open(archive, 'w:gz') as tf:
                for path in runner.RTL:
                    tf.add(runner.ROOT / path, arcname=path)
            rc, status, calls = self.invoke(['--baseline', '--baseline-archive', str(archive)])
            self.assertEqual(rc, 0)
            self.assertEqual(len(status['baseline_fingerprints']), 3)
            self.assertEqual(status['archive_sha256'], runner.sha(archive.read_bytes()))

    def test_missing_baseline_fails_before_launch(self):
        rc, status, calls = self.invoke(['--baseline'])
        self.assertEqual(status['state'], 'ERROR')
        self.assertEqual(calls, [])
        self.assertNotEqual(rc, 0)

    def test_explicit_missing_archive_not_silently_ignored(self):
        rc, status, calls = self.invoke(['--baseline-archive', '/nonexistent/required.tgz'])
        self.assertEqual(calls, [])
        self.assertNotEqual(rc, 0)

    def test_vcs_fatal_can_exit_zero(self):
        rc, status, calls = self.invoke(output='Fatal: fixture\nVLDU_SUITE_PASS\n')
        self.assertEqual(status['state'], 'FAIL')
        self.assertNotEqual(rc, 0)

    def test_nonfatal_error_overrides_pass_marker(self):
        rc, status, calls = self.invoke(output='Error: fixture\nVLDU_SUITE_PASS\n')
        self.assertEqual(status['state'], 'FAIL')

    def test_missing_marker_fails(self):
        self.assertEqual(self.invoke(output='normal exit\n')[1]['state'], 'FAIL')

    def test_compile_failure_never_launches(self):
        rc, status, calls = self.invoke(compile_exit=255)
        self.assertEqual(status['state'], 'COMPILE_FAILED')
        self.assertEqual(len(calls), 1)

    def test_nonzero_exit_rejects_success_text(self):
        self.assertEqual(self.invoke(run_exit=1)[1]['state'], 'FAIL')

    def test_image_mutation_rejected(self):
        self.assertEqual(self.invoke(mutate_image=True)[1]['state'], 'ERROR')

    def test_equivalence_requires_independent_reference(self):
        rc, status, calls = self.invoke(['--suite', 'mul'])
        self.assertEqual(status['state'], 'ERROR')
        self.assertEqual(calls, [])
        self.assertIn('no self-reference', status['error'])

    def test_equivalence_explicit_reference_without_archive(self):
        # Input-routing test only: subprocess is mocked, no numerical claim.
        reference = runner.ROOT / runner.RTL[0]
        rc, status, calls = self.invoke(['--suite', 'mul', '--reference-simd-mul', str(reference)],
                                       output='SIMD MUL equivalence PASS configurations=24\n')
        self.assertEqual(rc, 0)
        self.assertEqual(status['baseline_fingerprints'][runner.RTL[0]], runner.sha(reference.read_bytes()))


if __name__ == '__main__':
    unittest.main()
