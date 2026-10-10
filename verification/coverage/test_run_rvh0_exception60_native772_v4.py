"""V4 private binding and one-shot execution checks without launching EDA."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_rvh0_exception60_native772_v4 as launcher


class Gates(unittest.TestCase):
    def test_private_binding_preserves_predecessor(self):
        self.assertIs(launcher.run.__globals__['qualification'], launcher.qualification)
        self.assertIsNot(launcher.predecessor.qualification, launcher.qualification)
        worker = launcher.worker()
        self.assertEqual(worker.__globals__['ENTRY'], launcher.qualification.ENTRY)
        self.assertIs(worker.__globals__['verify'], launcher.qualification.inspect)

    def test_unreviewed_configuration_rejected(self):
        with patch.object(launcher.qualification, 'verify_config') as check:
            with self.assertRaises(ValueError):
                launcher.run(Path('/unused'), 'sealed', 'different')
            check.assert_not_called()

    def test_exact_reviewed_fresh_configuration_and_no_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            factory = Mock()
            with patch.object(launcher.qualification, 'verify_config',
                              return_value={'output': str(output)}), \
                    patch.dict(launcher.run.__globals__, worker=factory):
                launcher.run(output, 'sealed', 'sealed')
                factory.return_value.assert_called_once_with(output, 'sealed')
                for name in ('execution.json', 'terminal.json', 'launcher.log', 'capture-result.json'):
                    path = output / name
                    path.touch()
                    factory.reset_mock()
                    with self.assertRaises(ValueError):
                        launcher.run(output, 'sealed', 'sealed')
                    factory.assert_not_called()
                    path.unlink()


if __name__ == '__main__':
    unittest.main()
