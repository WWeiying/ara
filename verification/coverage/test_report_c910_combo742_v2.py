from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import report_c910_combo742_v2 as report


class LaunchTests(unittest.TestCase):
    def test_adapter_has_actual_required_subprocess_members(self):
        adapter = report.subprocess_namespace(Popen='mock', TimeoutExpired='exception')
        self.assertEqual(adapter.Popen, 'mock')
        self.assertEqual(adapter.STDOUT, report.prior.base.subprocess.STDOUT)
        self.assertEqual(adapter.PIPE, report.prior.base.subprocess.PIPE)
        self.assertEqual(adapter.DEVNULL, report.prior.base.subprocess.DEVNULL)
        self.assertEqual(adapter.TimeoutExpired, 'exception')

    def test_actual_launch_body_reaches_identity_gate_not_attribute_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report.life.save(out / 'config.json', dict(pins={}, tool_identity={},
                                                    successor_entry=str(Path(report.__file__).resolve())))
            seal = report.life.digest(out / 'config.json')
            process = SimpleNamespace(pid=123, poll=lambda: 0)
            module = report.prior.base
            with patch.object(module.tools, 'revalidate'), \
                 patch.object(module.tools, 'controlled_environment', return_value={}), \
                 patch.object(module.tools, 'launch_command', return_value=['DVE_NOT_EXECUTED']), \
                 patch.object(module.tools, 'process_info', return_value={'starttime': 1}), \
                 patch.object(module.subprocess, 'Popen', return_value=process) as popen:
                with self.assertRaisesRegex(ValueError, 'No launch-bound DVE'):
                    report.run(out, seal)
                self.assertEqual(popen.call_args.kwargs['stderr'], module.subprocess.STDOUT)
                self.assertEqual(popen.call_args.kwargs['env']['DVE_REVIEWED_WAIVERS'],
                                 str(report.prior.TCL))

    def test_original_failure_reproduced_by_actual_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report.life.save(out / 'config.json', dict(pins={}, tool_identity={}))
            seal = report.life.digest(out / 'config.json')
            module = report.prior.base
            with patch.object(module.tools, 'revalidate'), \
                 patch.object(module.tools, 'controlled_environment', return_value={}), \
                 patch.object(module.tools, 'launch_command', return_value=['DVE_NOT_EXECUTED']):
                with self.assertRaisesRegex(AttributeError, 'STDOUT'):
                    report.prior.run(out, seal)

    def test_predecessor_frozen_hashes(self):
        report.life.check(report.PINS)


if __name__ == '__main__':
    unittest.main()
