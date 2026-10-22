from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_gap59_system_batch as batch


class Gap59Tests(unittest.TestCase):
    def test_exact_case_registry(self):
        with patch.object(batch.previous, 'CATALOG', batch.CATALOG):
            self.assertEqual(batch.previous.adapter_names([
                {'name': 'rvv:sv39_gap52_superpage_sfence_pmp0'}
            ]), ['run_gap52_system_checked_extension'])

    def test_other_cases_rejected(self):
        with patch.object(batch.previous, 'CATALOG', batch.CATALOG):
            for name in ('app:sv39_gap52_superpage_sfence_pmp0',
                         'rvv:sv39_gap52_superpage_sfence_pmp1',
                         'rvv:vgap47_sv39_indexed_pmp0',
                         'app:qbs_gap51_payload_matrix'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    batch.previous.adapter_names([{'name': name}])

    def test_parent_pinned_before_admission_and_rechecked(self):
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
            result = batch.bind_previous(validate)('draft')
        self.assertEqual(events, ['pin', 'validate', 'recheck'])
        self.assertEqual(result, (proof, ['row'], ['case']))
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
