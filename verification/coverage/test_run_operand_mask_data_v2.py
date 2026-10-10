import unittest
from unittest.mock import patch
import run_operand_mask_data_v2 as run


class TerminalTests(unittest.TestCase):
    def test_only_terminal_watch_added(self):
        before = run.previous.command(run.OUT)
        after = run.command(run.OUT)
        self.assertEqual(after[:-1], before)
        self.assertEqual(after[-1], '+COMMIT_TOHOST=80001000')
        self.assertEqual(run.previous.BUDGET, 1800)

    def test_private_namespace_keeps_exact_architecture_gates(self):
        ns = run.namespace()
        self.assertIs(ns['shared'], run.previous.shared)
        self.assertIs(ns['lifecycle'], run.previous.lifecycle)
        self.assertEqual(ns['ELF'], run.previous.ELF)
        self.assertNotEqual(ns['OUT'], run.previous.OUT)

    def test_wrong_terminal_rejected(self):
        with patch.object(run.previous.json, 'loads', return_value={'symbols': {'tohost': 0}}):
            with self.assertRaises(ValueError): run.command(run.OUT)


if __name__ == '__main__': unittest.main()
