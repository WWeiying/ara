import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run_readonly_csr_simulation as r


class RunnerTests(unittest.TestCase):
    def test_exact_command_and_budget(self):
        out = r.life.OUT / 'readonly-csr-test-run'; pre = r.life.OUT / 'readonly-csr-test-pre'
        cmd = r.command(out, pre)
        self.assertEqual(cmd[0], str(r.life.IMAGE)); self.assertEqual(cmd.count('+NO_FSDB'), 1)
        self.assertEqual([x for x in cmd if x.startswith('+PRELOAD=')], ['+PRELOAD=' + str(pre / 'input.elf')])
        self.assertIn('+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), cmd)
        self.assertIn('+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), cmd)
        self.assertEqual(r.BUDGET, 600)

    def test_existing_run_rejected_before_preflight(self):
        with mock.patch.object(r.preflight, 'verify') as verify:
            with self.assertRaises(ValueError): r.prepare(r.life.OUT, r.life.OUT / 'pre', 'a' * 64)
            verify.assert_not_called()

    def test_foreign_output_rejected(self):
        with self.assertRaises(ValueError): r.prepare(Path('/tmp/csr-test'), r.life.OUT / 'pre', 'a' * 64)

    def test_changed_preflight_rejected(self):
        with mock.patch.object(r.preflight, 'verify', side_effect=ValueError('pin drift')):
            with self.assertRaisesRegex(ValueError, 'pin drift'):
                r.prepare(r.life.OUT / 'readonly-csr-uncreated-fixture', r.life.OUT / 'pre', 'a' * 64)

    def test_adapter_restores_frozen_globals_even_on_failure(self):
        out = r.life.OUT / 'readonly-csr-uncreated-fixture'
        manifest = dict(preflight=str(r.life.OUT / 'pre/preflight-manifest.json'), preflight_seal='a' * 64,
                        elf_sha256='b' * 64)
        previous = {k: getattr(r.frozen, k) for k in ('PRE', 'ELF_SEAL', 'preflight', 'command')}
        with mock.patch.object(r, 'prepare', return_value=manifest), mock.patch.object(r.frozen, 'run',
                side_effect=RuntimeError('mock only, no EDA')) as run:
            with self.assertRaises(RuntimeError): r.invoke_run(out, manifest)
            run.assert_called_once_with(out, manifest)
        self.assertEqual(previous, {k: getattr(r.frozen, k) for k in previous})

    def test_reviewed_manifest_drift_never_runs(self):
        manifest = dict(preflight=str(r.life.OUT / 'pre/preflight-manifest.json'), preflight_seal='a' * 64)
        with mock.patch.object(r, 'prepare', return_value={}), mock.patch.object(r.frozen, 'run') as run:
            with self.assertRaises(ValueError): r.invoke_run(r.life.OUT / 'uncreated', manifest)
            run.assert_not_called()


if __name__ == '__main__': unittest.main()
