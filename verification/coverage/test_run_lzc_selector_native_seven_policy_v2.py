import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_lzc_selector_native_seven_policy_v2 as subject


class SuccessorLaunchTests(unittest.TestCase):
    def test_actual_entry_globals_and_frozen_original_unchanged(self):
        self.assertIs(subject.main.__globals__, subject.__dict__)
        self.assertIs(subject.background.__globals__['SCRIPT'], subject.SCRIPT)
        self.assertIs(subject.invoke_run.__globals__['generic'], subject.generic)
        self.assertNotEqual(subject.SCRIPT, subject.prior.SCRIPT)
        self.assertIs(subject.prior.generic, subject.generic.prior)

    def test_exclusive_claim_no_retry(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            subject.frozen.write(root / 'status.json', {'status': 'PREPARED_NO_DVE'})
            subject.claim_once(root, 'successor-parent-seal', 'background')
            with self.assertRaises(ValueError):
                subject.claim_once(root, 'successor-parent-seal', 'background')

    def test_launch_entry_and_review_pin_actual_successor_no_eda(self):
        with tempfile.TemporaryDirectory(dir=subject.frozen.OUT) as temporary:
            root = Path(temporary)
            subject.frozen.write(root / 'status.json', {'status': 'PREPARED_NO_DVE'})
            runtime = {'population': 724, 'admission_sha256': 'formal724'}
            subject.frozen.write(root / 'runtime-plan.json', runtime)
            seal = subject.frozen.sha(root / 'runtime-plan.json')
            config = dict(pins={}, command=['NO_EDA'], population=724, admission_manifest_sha256='formal724')
            with patch.object(subject.generic, 'read_config', return_value=(None, config)), \
                 patch.object(subject.subprocess, 'Popen', side_effect=AssertionError('NO_EDA')):
                plan = subject.prepare_entry(root, seal)
                launch_seal = subject.frozen.sha(root / subject.PLAN)
                reviewed, _, _ = subject.reviewed_entry(root, launch_seal)
                self.assertEqual(plan, reviewed)
                self.assertEqual((plan['targets'], plan['protected'], plan['audited'], plan['timeout_seconds']), (5868, 17702, 23570, 10800))
                self.assertIn(str(subject.SCRIPT), plan['pins'])
                self.assertIn(str(subject.generic.SCRIPT), plan['pins'])
                self.assertFalse((root / subject.CLAIM).exists())
                del plan['pins'][str(subject.generic.TCL)]
                subject.frozen.write(root / subject.PLAN, plan)
                with self.assertRaisesRegex(ValueError, 'Unpinned'):
                    subject.reviewed_entry(root, subject.frozen.sha(root / subject.PLAN))

    def test_private_run_uses_successor_read_and_verify(self):
        root = subject.frozen.OUT / 'NEVER_EXECUTED_V2'
        plan, config = {'config_sha256': 'strict-seal'}, {'immutable': True}
        class Context:
            def namespace(self):
                return {}
        captured = {}
        def private(function, **bindings):
            captured.update(bindings)
            self.assertIs(function, subject.frozen.run)
            return lambda *args: None
        with patch.object(subject.generic.six, 'private', side_effect=private):
            subject.invoke_run(root, plan, Context(), config)
        with patch.object(subject.generic, 'read_config', return_value=(None, config)) as read:
            self.assertEqual(captured['read_config'](root, 'strict-seal'), config)
            read.assert_called_once_with(root, 'strict-seal')
        with patch.object(subject.generic, 'verify', return_value={'strict': True}) as verify:
            self.assertEqual(captured['verify_artifacts'](root, config), {'strict': True})
            verify.assert_called_once_with(root, 'strict-seal')


if __name__ == '__main__':
    unittest.main()
