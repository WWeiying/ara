from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_gap67_scalar_system_batch as batch


class Gap67Tests(unittest.TestCase):
    def test_exact_names_and_order(self):
        cases = [{'name': name} for name, _, _ in batch.CATALOG]
        with patch.object(batch.previous, 'CATALOG', batch.CATALOG):
            self.assertEqual(batch.previous.adapter_names(cases),
                             [module for _, _, module in batch.CATALOG])

    def test_unreviewed_names_rejected(self):
        with patch.object(batch.previous, 'CATALOG', batch.CATALOG):
            for name in ('app:scalar_gap63_zcb_reject', 'rvv:scalar_gap63_zcb_reject_extra',
                         'rvv:lr_gap64_wd_drain_pmp1', 'rvv:sv39_gap52_superpage_sfence_pmp0'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    batch.previous.adapter_names([{'name': name}])

    def test_adapter_locations(self):
        batch.validate_modules([
            SimpleNamespace(__name__=name, __file__=str(path))
            for name, path in batch.ADAPTER_PATHS.items()
        ])

    def test_shadowed_and_unknown_modules_rejected(self):
        for name in (*batch.ADAPTER_PATHS, 'unknown'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                batch.validate_modules([SimpleNamespace(__name__=name, __file__='/tmp/wrong.py')])

    def test_parent_pinned_and_rechecked(self):
        events = []
        inputs = Mock(files={str(batch.PREVIOUS): 'original'})
        inputs.pin.side_effect = lambda _: events.append('pin')
        proof = Mock()
        proof.hashes.side_effect = lambda _: events.append('recheck')

        def validate(selection):
            events.append('validate')
            self.assertEqual(selection, 'draft')
            return proof, ['row'], ['case']

        with patch.object(batch.previous.evidence, 'Evidence', return_value=inputs):
            self.assertEqual(batch.bind_previous(validate)('draft'), (proof, ['row'], ['case']))
        self.assertEqual(events, ['pin', 'validate', 'recheck'])
        inputs.pin.assert_called_once_with(batch.PREVIOUS)
        proof.hashes.assert_called_once_with({str(batch.PREVIOUS): 'original'})

    def test_parent_drift_rejected(self):
        inputs = Mock(files={str(batch.PREVIOUS): 'original'})
        proof = Mock()
        proof.hashes.side_effect = ValueError('parent changed')
        with patch.object(batch.previous.evidence, 'Evidence', return_value=inputs):
            with self.assertRaises(ValueError):
                batch.bind_previous(lambda _: (proof, [], []))('draft')

    def test_precheck_failure_propagated(self):
        with patch.object(batch.previous.evidence, 'Evidence'):
            validate = Mock(side_effect=ValueError('independent precheck failed'))
            with self.assertRaises(ValueError):
                batch.bind_previous(validate)('draft')


if __name__ == '__main__':
    unittest.main()
