"""Authorization and retry gates without launching EDA."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_rvh0_exception60_native772_v2 as runner


class RunGate(unittest.TestCase):
    def test_environment_adapter_preserves_mature_runner(self):
        function = runner.worker()
        self.assertIn(('DVE_COVERAGE_OUTPUT', 'RVH0_EXCEPTION60_SEAL'), function.__code__.co_consts)
        self.assertNotIn(('DVE_COVERAGE_OUTPUT', 'CVA6_PARENT_RVFI457_SEAL'), function.__code__.co_consts)
        self.assertIs(function.__globals__['verify'], runner.qualification.inspect)
        self.assertEqual(function.__globals__['ENTRY'], runner.qualification.ENTRY)

    def test_wrong_authorization_rejected_before_config(self):
        with patch.object(runner.qualification, 'verify_config') as check:
            with self.assertRaises(ValueError):
                runner.run(Path('/unused'), 'sealed', 'different')
            check.assert_not_called()

    def test_fresh_run_and_restart_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            with patch.object(runner.qualification, 'verify_config', return_value={'output': str(output)}), \
                    patch.object(runner, 'worker') as factory:
                runner.run(output, 'sealed', 'sealed')
                factory.return_value.assert_called_once_with(output, 'sealed')
                for name in ('execution.json', 'terminal.json', 'launcher.log', 'capture-result.json'):
                    path = output / name
                    path.touch()
                    factory.reset_mock()
                    with self.assertRaises(ValueError):
                        runner.run(output, 'sealed', 'sealed')
                    factory.assert_not_called()
                    path.unlink()


if __name__ == '__main__':
    unittest.main()
