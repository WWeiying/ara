"""V3 private namespace, authorization and no-retry checks; no EDA."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_rvh0_exception60_native772_v3 as launcher


class Gates(unittest.TestCase):
    def test_private_v3_binding_not_global_mutation(self):
        self.assertIs(launcher.run.__globals__['qualification'], launcher.qualification)
        self.assertIsNot(launcher.predecessor.qualification, launcher.qualification)
        worker = launcher.worker()
        self.assertEqual(worker.__globals__['ENTRY'], launcher.qualification.ENTRY)
        self.assertIs(worker.__globals__['verify'], launcher.qualification.inspect)

    def test_unreviewed_seal_rejected(self):
        with patch.object(launcher.qualification, 'verify_config') as check:
            with self.assertRaises(ValueError):
                launcher.run(Path('/unused'), 'sealed', 'other')
            check.assert_not_called()

    def test_reviewed_fresh_and_restart_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            factory = Mock()
            with patch.object(launcher.qualification, 'verify_config', return_value={'output': str(output)}), \
                    patch.dict(launcher.run.__globals__, worker=factory):
                launcher.run(output, 'sealed', 'sealed')
                factory.return_value.assert_called_once_with(output, 'sealed')
                (output / 'execution.json').touch()
                factory.reset_mock()
                with self.assertRaises(ValueError):
                    launcher.run(output, 'sealed', 'sealed')
                factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
