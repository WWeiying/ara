"""Actual constructor context and default forwarding, with no DVE."""
import inspect
import unittest
from unittest.mock import patch
import eight_policy_epoch_735_report_v3 as r


class Reader(unittest.TestCase):
    def test_constructor_forwards_exact_original_defaults(self):
        with patch.object(r.prior.wiring.Wiring, '__init__', return_value=None) as original:
            r.Wiring({}, [], [])
        original.assert_called_once_with({}, [], [], None, links=None, max_bytes=805306368)

    def test_check_inputs_defaults_and_explicit_boundaries(self):
        owner = object.__new__(r.Wiring)
        with patch.object(r.prior.wiring.Wiring, 'check_inputs', return_value='checked') as original:
            self.assertEqual(owner.check_inputs({}), 'checked')
            original.assert_called_with({}, boundary=None)
            owner.check_inputs({}, boundary='live')
            original.assert_called_with({}, boundary='live')

    def test_signature_matches_frozen_original(self):
        old = r.prior.prior.wiring_base.Wiring
        self.assertEqual(inspect.signature(r.Wiring.__init__), inspect.signature(old.__init__))
        self.assertEqual(inspect.signature(r.Wiring.check_inputs), inspect.signature(old.check_inputs))

    def test_actual_constructor_has_no_keyword_defaults_failure(self):
        # Enter the real constructor with an empty phase. Any accidental read is
        # rejected; constructing the Context itself must not consume source bytes.
        owner = r.Wiring({}, [], [])
        self.assertEqual(owner.context.population, 735)
        self.assertEqual(owner.context.admission, r.prior.prior.ADMISSION)
        self.assertIs(owner.context.check_config.__func__.__code__,
                      r.prior.prior.wiring.population.Context.check_config.__code__)

    def test_no_frozen_reader_mutation(self):
        self.assertIs(r.prior.report.check.__globals__['wiring'], r.prior.wiring)
        self.assertIs(r.report.check.__globals__['wiring'], r.wiring)
        self.assertIn(r.ROOT / r.prior.PLAN, r.dependencies())

    def test_foreign_output_cannot_reuse_or_reprepare(self):
        with self.assertRaisesRegex(Exception, 'exact completed735'):
            r.prepare(r.ROOT.with_name('foreign'))


if __name__ == '__main__':
    unittest.main()
