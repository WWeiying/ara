import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import run_six_policy_population as subject


def fake_frozen_run(output, seal):
    config = read_config(output, seal)
    return verify_artifacts(output, config)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'prepared'
        self.output.mkdir()
        self.config = dict(pins={}, population=723, admission_manifest_sha256='a' * 64,
                           targets=5808, protected=13562, command=['dve', '-script', 'sealed.tcl'],
                           run_timeout_seconds=subject.frozen.TIMEOUT)
        subject.frozen.write(self.output / 'config.json', self.config)
        subject.frozen.write(self.output / 'status.json', {'status': 'PREPARED_NO_DVE'})
        self.seal = subject.frozen.sha(self.output / 'config.json')
        self.context = SimpleNamespace(namespace=lambda: {}, check_config=lambda config, output: None)
        self.addCleanup(patch.stopall)
        patch.object(subject.frozen, 'OUT', self.root).start()
        self.read = patch.object(subject.generic, 'read_config', return_value=(self.context, self.config)).start()

    def prepare(self):
        subject.prepare_entry(self.output, self.seal)
        return subject.frozen.sha(self.output / subject.PLAN)

    def test_prepare_additive_no_eda_config_unchanged(self):
        before = (self.output / 'config.json').read_bytes()
        with patch.object(subject.subprocess, 'Popen') as popen:
            seal = self.prepare()
            subject.reviewed_entry(self.output, seal)
        popen.assert_not_called()
        self.assertEqual((self.output / 'config.json').read_bytes(), before)
        self.assertFalse((self.output / subject.CLAIM).exists())
        self.assertFalse((self.output / 'DVEfiles').exists())

    def test_wrong_seal_or_dependency_drift_rejected(self):
        seal = self.prepare()
        with self.assertRaises(ValueError):
            subject.reviewed_entry(self.output, '0' * 64)
        (self.output / 'config.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'dependency drift'):
            subject.reviewed_entry(self.output, seal)

    def test_no_reprepare_or_run_artifacts(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'already sealed'):
            subject.prepare_entry(self.output, self.seal)
        for name in ('DVEfiles', 'execution.json', 'live-ready'):
            path = self.output / name
            path.touch()
            with self.assertRaisesRegex(ValueError, 'Preexisting'):
                subject.claim_once(self.output, 's', 'foreground')
            path.unlink()

    def test_atomic_claim_no_retry(self):
        subject.claim_once(self.output, 's', 'foreground')
        with self.assertRaises(ValueError):
            subject.claim_once(self.output, 's', 'foreground')
        subject.frozen.write(self.output / 'status.json', {'status': 'FAILED'})
        with self.assertRaisesRegex(ValueError, 'No repeat'):
            subject.unstarted(self.output)

    def test_private_frozen_run_adapter_no_global_mutation(self):
        before = dict(fake_frozen_run.__globals__)
        plan = dict(config_sha256=self.seal)
        with patch.object(subject.frozen, 'run', fake_frozen_run), \
             patch.object(subject.generic, 'verify', return_value={'application_approval': False}) as verify:
            subject.invoke_run(self.output, plan, self.context, self.config)
        verify.assert_called_once_with(self.output, self.seal)
        self.assertEqual(fake_frozen_run.__globals__, before)

    def test_run_claim_before_frozen_lifecycle(self):
        seal = self.prepare()
        def called(output, plan, context, config):
            self.assertTrue((output / subject.CLAIM).is_file())
            raise RuntimeError('simulated lifecycle failure')
        with patch.object(subject, 'invoke_run', side_effect=called):
            with self.assertRaisesRegex(RuntimeError, 'simulated'):
                subject.run_reviewed(self.output, seal)
            with self.assertRaises(ValueError):
                subject.run_reviewed(self.output, seal)

    def test_changed_command_timeout_or_protection_rejected(self):
        seal = self.prepare()
        for key, value in (('command', ['wrong']), ('targets', 5807), ('protected', 13561),
                           ('run_timeout_seconds', 1)):
            changed = copy.deepcopy(self.config)
            changed[key] = value
            with patch.object(subject.generic, 'read_config', return_value=(self.context, changed)):
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    subject.reviewed_entry(self.output, seal)

    def test_verify_uses_generic_adapter_not_frozen717_label(self):
        seal = self.prepare()
        with patch.object(subject.generic, 'verify', return_value={'application_approval': False}) as verify, \
             patch('builtins.print'):
            subject.main(['verify', '--output', str(self.output), '--launch-seal', seal])
        verify.assert_called_once_with(self.output, self.seal)

    def test_background_handshake_and_single_spawn(self):
        seal = self.prepare()
        child = Mock(pid=12345)
        with patch.object(subject.subprocess, 'Popen', return_value=child) as popen:
            record = subject.background(self.output, seal)
            self.assertFalse(record['actual_dve_pid_confirmed'])
            self.assertEqual(record['runner_pid'], 12345)
            self.assertEqual(popen.call_args.kwargs['cwd'], self.output)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            child.stdin.write.assert_called_once_with(b'SEALED_PARENT_RECORD_READY\n')
            with self.assertRaises(ValueError):
                subject.background(self.output, seal)
            self.assertEqual(popen.call_count, 1)

    def test_failed_background_spawn_stays_claimed(self):
        seal = self.prepare()
        with patch.object(subject.subprocess, 'Popen', side_effect=OSError('mock spawn failure')):
            with self.assertRaises(OSError):
                subject.background(self.output, seal)
        self.assertTrue((self.output / subject.CLAIM).exists())
        with self.assertRaises(ValueError):
            subject.run_reviewed(self.output, seal)

    def test_background_consumer_wrong_pid_rejected(self):
        seal = self.prepare()
        subject.claim_once(self.output, seal, 'background')
        subject.frozen.write(self.output / 'population-background.json', {'runner_pid': -1})
        with patch.object(subject, 'invoke_run') as invoke:
            with self.assertRaisesRegex(ValueError, 'consumer PID'):
                subject.run_reviewed(self.output, seal, claimed=True)
        invoke.assert_not_called()


if __name__ == '__main__':
    unittest.main()
