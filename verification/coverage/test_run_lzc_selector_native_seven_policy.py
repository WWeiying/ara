import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_lzc_selector_native_seven_policy as subject


class LaunchTests(unittest.TestCase):
    def test_claim_exclusive_failure_not_retryable(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            subject.frozen.write(root / 'status.json', {'status': 'PREPARED_NO_DVE'})
            subject.claim_once(root, 'parent-seal', 'background')
            with self.assertRaises(ValueError):
                subject.claim_once(root, 'parent-seal', 'background')
            self.assertEqual(json.loads((root / subject.CLAIM).read_bytes())['launch_plan_sha256'], 'parent-seal')

    def test_private_frozen_run_seven_verifier_not_frozen_six(self):
        root = subject.frozen.OUT / 'NOT_EXECUTED_SEVEN_STUB'
        config = {'one': 'sealed'}
        plan = {'config_sha256': 'runtime-seal'}
        class Context:
            def namespace(self):
                return {'sentinel': 'preserved'}
        captured = {}
        def private(function, **bindings):
            captured.update(bindings)
            self.assertIs(function, subject.frozen.run)
            return lambda *args: None
        with patch.object(subject.generic.six, 'private', side_effect=private):
            subject.invoke_run(root, plan, Context(), config)
        with patch.object(subject.generic, 'read_config', return_value=(None, config)):
            self.assertEqual(captured['read_config'](root, 'runtime-seal'), config)
            with self.assertRaises(ValueError):
                captured['read_config'](root, 'other-seal')
        with patch.object(subject.generic, 'verify', return_value={'seven': True}) as verify:
            self.assertEqual(captured['verify_artifacts'](root, config), {'seven': True})
            verify.assert_called_once_with(root, 'runtime-seal')
        self.assertEqual(captured['sentinel'], 'preserved')

    def test_main_bound_to_successor_no_frozen_global_mutation(self):
        self.assertIs(subject.main.__globals__, subject.__dict__)
        self.assertIs(subject.background.__globals__['SCRIPT'], subject.SCRIPT)
        self.assertNotEqual(subject.SCRIPT, subject.prior.SCRIPT)
        self.assertIs(subject.prior.generic, subject.generic.six.prior)

    def test_prepare_entry_no_launch_and_exact_counts(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            subject.frozen.write(root / 'status.json', {'status': 'PREPARED_NO_DVE'})
            runtime = dict(population=724, admission_sha256='formal724')
            subject.frozen.write(root / 'runtime-plan.json', runtime)
            seal = subject.frozen.sha(root / 'runtime-plan.json')
            config = dict(pins={}, command=['NOT_AN_EDA_COMMAND'])
            with patch.object(subject.generic, 'read_config', return_value=(None, config)), \
                 patch.object(subject.subprocess, 'Popen', side_effect=AssertionError('NO_LAUNCH')):
                plan = subject.prepare_entry(root, seal)
            self.assertEqual((plan['targets'], plan['protected'], plan['audited']), (5868, 17702, 23570))
            self.assertEqual(plan['timeout_seconds'], 10800)
            self.assertFalse(plan['launch_approved'])
            self.assertFalse((root / subject.CLAIM).exists())


if __name__ == '__main__':
    unittest.main()
