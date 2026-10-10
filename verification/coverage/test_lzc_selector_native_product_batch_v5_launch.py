"""Offline smoke prerequisite and frozen lifecycle binding tests; no EDA launch."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import lzc_selector_native_product_batch_v5_launch as launch

OUT = launch.v4.batch.product.OUT
FULL = OUT / 'lzc_selector_native_product_batch-707-20261006-05'
SMOKE = OUT / 'lzc_selector_native_product_guard-smoke-707-20261006-01'


class V5LaunchTests(unittest.TestCase):
    def test_actual_sealed_smoke_gate_and_full_inputs(self):
        full, result, saved = launch.verified_inputs(FULL, SMOKE)
        self.assertEqual(len(full['targets']), 120)
        self.assertEqual(len(full['protection_rows']), 4200)
        self.assertEqual(result['runtime_patchlevel'], '8.4.5.1')
        self.assertEqual(result['singleton_binding']['position'], 47)
        self.assertEqual(result['singleton_binding']['native_record']['native_id'], '20')
        self.assertEqual(result['singleton_binding']['native_record']['vector_id'], '2')
        self.assertTrue(result['final_reset_empty'])
        self.assertEqual(result['qualified_candidates'], 0)
        self.assertEqual(saved['runtime_patchlevel'], result['runtime_patchlevel'])

    def test_missing_smoke_result_rejected_before_launch(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_launch_negative-') as temp:
            with mock.patch.object(launch.v5, 'reviewed_probe', return_value=({'full_prepare': str(FULL)}, {})), \
                 mock.patch.object(launch.v4.subprocess, 'Popen') as process:
                with self.assertRaises(FileNotFoundError):
                    launch.verified_inputs(FULL, Path(temp))
                process.assert_not_called()

    def test_lifecycle_is_same_code_with_private_v5_bindings(self):
        original = (launch.v4.SCRIPT, launch.v4.reviewed_plan, launch.v4.verify, launch.v4.__file__)
        for name in ('background', 'run'):
            adapted = launch.lifecycle(name)
            self.assertIs(adapted.__code__, getattr(launch.v4, name).__code__)
            self.assertIsNot(adapted.__globals__, launch.v4.__dict__)
            self.assertEqual(adapted.__globals__['SCRIPT'], launch.v5.FULL)
            self.assertIs(adapted.__globals__['reviewed_plan'], launch.reviewed_plan)
            self.assertIs(adapted.__globals__['verify'], launch.verify)
        self.assertEqual(original, (launch.v4.SCRIPT, launch.v4.reviewed_plan, launch.v4.verify, launch.v4.__file__))

    def test_background_worker_uses_new_wrapper_and_never_repeats(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_background_unit-') as temp:
            output = Path(temp)
            (output / 'batch-plan.json').write_text('{}')
            adapted = launch.lifecycle('background')
            adapted.__globals__['reviewed_plan'] = mock.Mock(return_value={})
            with mock.patch.object(launch.v4.subprocess, 'Popen', return_value=mock.Mock(pid=12345)) as process:
                adapted(output)
                command = process.call_args.args[0]
                self.assertEqual(command[1], str(Path(launch.__file__).resolve()))
                self.assertEqual(command[2], 'run-reviewed-measurement')
                with self.assertRaises(ValueError):
                    adapted(output)
                self.assertEqual(process.call_count, 1)

    def test_run_lifecycle_preserves_v5_command_watchdog_and_failure_no_retry(self):
        with tempfile.TemporaryDirectory(dir=OUT, prefix='lzc_selector_native_run_unit-') as temp:
            output = Path(temp)
            (output / 'batch-plan.json').write_text('{}')
            launch.write(output / 'reviewed-start.json', dict(
                status='PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED',
                batch_plan_sha256=launch.sha(output / 'batch-plan.json')))
            plan = json.loads((FULL / 'batch-plan.json').read_bytes())
            adapted = launch.lifecycle('run')
            adapted.__globals__['reviewed_plan'] = mock.Mock(return_value=plan)
            native = mock.Mock(pid=12345)
            native.wait.return_value = 1
            native.poll.return_value = 1
            with mock.patch.object(launch.v4.subprocess, 'Popen', return_value=native) as process:
                with self.assertRaises(ValueError):
                    adapted(output)
                self.assertEqual(process.call_count, 1)
                self.assertEqual(process.call_args.args[0], plan['command'])
                native.wait.assert_called_once_with(timeout=10530)
            status = json.loads((output / 'batch-status.json').read_bytes())
            self.assertEqual(status['status'], 'FAILED_RECORDED_NOT_QUALIFICATION')
            self.assertEqual(status['actual_script'], str(launch.v5.FULL))
            self.assertFalse(status['final_application_approval'])


if __name__ == '__main__':
    unittest.main()
