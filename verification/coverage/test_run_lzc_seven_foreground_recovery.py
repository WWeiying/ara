import json
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_lzc_seven_foreground_recovery as subject


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=subject.frozen.OUT)
        root = Path(self.temporary.name)
        self.output, self.sidecar = root / 'original', root / 'recovery'
        self.output.mkdir()
        for group in (*subject.frozen.GROUPS, 'lzc'):
            (self.output / group).mkdir()
        command = ['NO_EDA_TEST_COMMAND']
        runtime = dict(command=command)
        subject.frozen.write(self.output / 'runtime-plan.json', runtime)
        runtime_sha = subject.frozen.sha(self.output / 'runtime-plan.json')
        launch = dict(command=command, config_sha256=runtime_sha, targets=5868,
                      protected=17702, audited=23570, timeout_seconds=10800)
        subject.frozen.write(self.output / subject.original.PLAN, launch)
        launch_sha = subject.frozen.sha(self.output / subject.original.PLAN)
        claim = dict(mode='background', owner_pid=3077991, output=str(self.output),
                     launch_plan_sha256=launch_sha, retries_allowed=False)
        background = dict(runner_pid=3080799, cwd=str(self.output), actual_dve_pid_confirmed=False,
                          automatic_retry=False, launch_plan_sha256=launch_sha, dve_command=command,
                          command=['/usr/bin/python3', '-B', str(subject.original.SCRIPT), '_background-worker',
                                   '--output', str(self.output), '--launch-seal', launch_sha])
        subject.frozen.write(self.output / subject.original.CLAIM, claim)
        subject.frozen.write(self.output / 'population-background.json', background)
        subject.frozen.write(self.output / 'status.json', dict(status='PREPARED_NO_DVE', application_approval=False))
        (self.output / 'population-runner.log').write_bytes(b'')
        values = dict(OUTPUT=self.output, SIDECAR=self.sidecar, LAUNCH_SEAL=launch_sha, RUNTIME_SEAL=runtime_sha,
                      CLAIM_SHA=subject.frozen.sha(self.output / subject.original.CLAIM),
                      BACKGROUND_SHA=subject.frozen.sha(self.output / 'population-background.json'),
                      STATUS_SHA=subject.frozen.sha(self.output / 'status.json'))
        self.constants = patch.multiple(subject, **values)
        self.constants.start()
        self.addCleanup(self.constants.stop)
        self.addCleanup(self.temporary.cleanup)

    def prepare(self):
        subject.prepare(self.sidecar)
        return subject.frozen.sha(self.sidecar / 'recovery-plan.json')

    def test_prepare_review_is_no_eda_original_records_preserved(self):
        before = [(self.output / n).read_bytes() for n in (subject.original.CLAIM, 'population-background.json')]
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('NO_SPAWN')):
            seal = self.prepare()
            plan = subject.reviewed(self.sidecar, seal)
        self.assertEqual((plan['targets'], plan['protected'], plan['audited']), (5868, 17702, 23570))
        self.assertFalse(plan['launch_approved'])
        self.assertFalse((self.sidecar / 'recovery-receipt.json').exists())
        self.assertEqual(before, [(self.output / n).read_bytes() for n in (subject.original.CLAIM, 'population-background.json')])

    def test_all_existing_execution_and_group_states_rejected(self):
        for name in subject.BLOCKED:
            path = self.output / name
            path.write_bytes(b'')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'execution/output'):
                subject.fast_guard()
            path.unlink()
        path = self.output / 'lzc/states_before.tsv'
        path.write_bytes(b'partial measurement')
        with self.assertRaisesRegex(ValueError, 'group audit'):
            subject.fast_guard()

    def test_old_pid_live_rejected_and_frozen_state_precedes_spawn(self):
        exists = Path.exists
        def mocked(path):
            return True if path == Path('/proc/3080799') else exists(path)
        with patch.object(Path, 'exists', mocked), self.assertRaisesRegex(ValueError, 'PID still exists'):
            subject.fast_guard()
        source = inspect.getsource(subject.frozen.run)
        self.assertLess(source.index("write(output / 'status.json', status)"), source.index('subprocess.Popen'))
        self.assertLess(source.index("write(output / 'integrity-before.json'"), source.index('subprocess.Popen'))

    def test_status_diagnostic_and_original_record_drift_rejected(self):
        status = self.output / 'status.json'
        data = status.read_bytes()
        for state in ('RUNNING', 'FAILED', 'COMPLETED'):
            subject.frozen.write(status, {'status': state})
            with self.subTest(state=state), self.assertRaises(ValueError):
                subject.fast_guard()
        status.write_bytes(data)
        (self.output / 'population-runner.log').write_text('Traceback: another cause')
        with self.assertRaisesRegex(ValueError, 'diagnostic'):
            subject.fast_guard()
        (self.output / 'population-runner.log').write_bytes(b'')
        (self.output / subject.original.CLAIM).write_text('drift')
        with self.assertRaisesRegex(ValueError, 'claim/background'):
            subject.fast_guard()

    def test_parent_authorization_and_review_seal_required(self):
        seal = self.prepare()
        with patch.object(subject.original, 'invoke_run', side_effect=AssertionError('NO_EDA')):
            with self.assertRaisesRegex(ValueError, 'parent'):
                subject.run(self.sidecar, seal, False)
            with self.assertRaises(ValueError):
                subject.run(self.sidecar, '0' * 64, True)
        self.assertFalse((self.sidecar / 'recovery-receipt.json').exists())

    def test_foreground_direct_invoke_no_spawn_one_shot_and_original_claim_unchanged(self):
        seal = self.prepare()
        before = [(self.output / n).read_bytes() for n in (subject.original.CLAIM, 'population-background.json')]
        launch = {'config_sha256': subject.RUNTIME_SEAL}
        config = {'command': ['NO_EDA_TEST_COMMAND']}
        with patch.object(subject.original, 'reviewed_entry', return_value=(launch, 'context', config)), \
             patch.object(subject.original, 'invoke_run') as invoke, \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('NO_BACKGROUND_SPAWN')):
            result = subject.run(self.sidecar, seal, True)
            invoke.assert_called_once_with(self.output, launch, 'context', config)
            self.assertEqual(result['owner_pid'], os.getpid())
            self.assertTrue(result['foreground_main'])
            with self.assertRaises(ValueError):
                subject.run(self.sidecar, seal, True)
        self.assertEqual(before, [(self.output / n).read_bytes() for n in (subject.original.CLAIM, 'population-background.json')])

    def test_failure_consumes_recovery_no_automatic_retry(self):
        seal = self.prepare()
        config = {'command': ['NO_EDA_TEST_COMMAND']}
        with patch.object(subject.original, 'reviewed_entry', return_value=({}, None, config)), \
             patch.object(subject.original, 'invoke_run', side_effect=RuntimeError('mock execution failure')):
            with self.assertRaises(RuntimeError):
                subject.run(self.sidecar, seal, True)
        receipt = json.loads((self.sidecar / 'recovery-receipt.json').read_bytes())
        self.assertEqual(receipt['status'], 'RECOVERY_FAILED_NO_AUTOMATIC_RETRY')
        with self.assertRaises(ValueError):
            subject.run(self.sidecar, seal, True)

    def test_existing_receipt_exclusive_and_dependency_omission_rejected(self):
        seal = self.prepare()
        path = self.sidecar / 'recovery-receipt.json'
        path.write_text('another owner')
        with self.assertRaises(FileExistsError):
            subject.run(self.sidecar, seal, True)
        self.assertEqual(path.read_text(), 'another owner')
        plan = json.loads((self.sidecar / 'recovery-plan.json').read_bytes())
        del plan['pins'][str(subject.SCRIPT)]
        subject.frozen.write(self.sidecar / 'recovery-plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'dependency omitted'):
            subject.reviewed(self.sidecar, subject.frozen.sha(self.sidecar / 'recovery-plan.json'))

    def test_host_setsid_inherits_cgroup_real_non_eda_child(self):
        parent = Path('/proc/self/cgroup').read_text()
        code = 'import os,json;from pathlib import Path;print(json.dumps(dict(pid=os.getpid(),sid=os.getsid(0),cgroup=Path("/proc/self/cgroup").read_text())))'
        child = subprocess.run([sys.executable, '-B', '-c', code], start_new_session=True,
                               check=True, capture_output=True, text=True)
        data = json.loads(child.stdout)
        self.assertEqual(data['sid'], data['pid'])
        self.assertNotEqual(data['sid'], os.getsid(0))
        self.assertEqual(data['cgroup'], parent)


if __name__ == '__main__':
    unittest.main()
