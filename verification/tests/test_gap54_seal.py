import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_gap54_akv_sealed_extension as gate
import run_gap55_sealed_batch as batch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix='gap54-akv-preflight-unit-', dir=gate.evidence.full.ROOT / 'verification/out')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = self.root / 'evidence.json'
        self.write(self.record, {'fixture_only': True})
        self.item = {'name': gate.original.admission.TEST,
                     'precheck': {'record': str(self.record)}}
        self.result = {'status': 'PASS', 'scope': 'fixture-only'}
        self.draft = {'cases': [self.item], 'baseline': 'fixture'}
        self.write(self.root / 'draft.json', self.draft)
        self.seal = {'status': 'PASS', 'vcs_launched': False,
                     'draft': str(self.root / 'draft.json'),
                     'draft_sha256': digest(self.root / 'draft.json'),
                     'case_sha256': gate.original.admission.oracle.canonical(self.item),
                     'result': copy.deepcopy(self.result),
                     'checked_files': {str(self.record): digest(self.record)}}
        self.reseal()

    def write(self, path, value):
        path.write_text(json.dumps(value, sort_keys=True))

    def reseal(self):
        path = self.root / 'sealed-precheck.json'
        self.write(path, self.seal)
        self.binding = {'path': str(path), 'sha256': digest(path),
                        'result': copy.deepcopy(self.result)}
        self.selection = dict(self.draft, sealed_precheck=self.binding)
        self.write(self.root / 'selection.json', self.selection)

    def delegate(self, item, proof):
        self.assertEqual(item, self.item)
        proof.pin(self.record)
        return copy.deepcopy(self.result)

    def check(self):
        proof = gate.evidence.Evidence()
        return gate.sealed_precheck(self.item, proof, self.delegate), proof

    def test_seal_draft_selection_and_original_proof_bound(self):
        result, proof = self.check()
        self.assertEqual(result, self.result)
        for name in ('selection.json', 'draft.json', 'sealed-precheck.json', 'evidence.json'):
            self.assertEqual(proof.files[str(self.root / name)], digest(self.root / name))
        self.assertIn(str(gate.SCRIPT), proof.files)
        self.assertIn(str(Path(gate.original.__file__).resolve()), proof.files)

    def test_missing_seal_rejected_before_delegate(self):
        (self.root / 'sealed-precheck.json').unlink()
        delegate = Mock()
        with self.assertRaises(ValueError):
            gate.sealed_precheck(self.item, gate.evidence.Evidence(), delegate)
        delegate.assert_not_called()

    def test_seal_hash_drift_rejected(self):
        self.write(self.root / 'sealed-precheck.json', dict(self.seal, extra=True))
        with self.assertRaises(ValueError): self.check()

    def test_mandatory_seal_digest_cannot_be_null_or_malformed(self):
        for digest_value in (None, '', 0, 'g' * 64, 'a' * 63):
            self.selection['sealed_precheck']['sha256'] = digest_value
            self.write(self.root / 'selection.json', self.selection)
            with self.subTest(digest_value=digest_value), self.assertRaises(ValueError): self.check()

    def test_mandatory_draft_digest_cannot_be_null_or_malformed(self):
        for digest_value in (None, '', 0, 'g' * 64, 'a' * 63):
            self.seal['draft_sha256'] = digest_value
            self.reseal()
            with self.subTest(digest_value=digest_value), self.assertRaises(ValueError): self.check()

    def test_nonpass_or_executed_seal_rejected(self):
        original = copy.deepcopy(self.seal)
        for change in ({'status': 'PENDING'}, {'vcs_launched': True}, {'vcs_launched': 0}):
            self.seal = dict(original, **change)
            self.reseal()
            with self.subTest(change=change), self.assertRaises(ValueError): self.check()

    def test_changed_saved_result_rejected(self):
        self.seal['result']['scope'] = 'different'
        self.reseal()
        with self.assertRaises(ValueError): self.check()

    def test_changed_selection_result_rejected(self):
        self.selection['sealed_precheck']['result']['scope'] = 'different'
        self.write(self.root / 'selection.json', self.selection)
        with self.assertRaises(ValueError): self.check()

    def test_deleted_or_extra_checked_file_rejected(self):
        for files in ({}, {str(self.record): digest(self.record), '/unexpected': '0' * 64}):
            self.seal['checked_files'] = files
            self.reseal()
            with self.subTest(files=files), self.assertRaises(ValueError): self.check()

    def test_wrong_checked_digest_rejected(self):
        self.seal['checked_files'][str(self.record)] = '0' * 64
        self.reseal()
        with self.assertRaises(ValueError): self.check()

    def test_complete_case_hash_rejected(self):
        self.seal['case_sha256'] = '0' * 64
        self.reseal()
        with self.assertRaises(ValueError): self.check()

    def test_original_draft_hash_rejected(self):
        self.write(self.root / 'draft.json', dict(self.draft, unexpected=True))
        with self.assertRaises(ValueError): self.check()

    def test_extra_case_in_original_selection_rejected(self):
        self.selection['cases'] = [self.item, self.item]
        self.write(self.root / 'selection.json', self.selection)
        with self.assertRaises(ValueError): self.check()

    def test_changed_draft_even_after_rehash_rejected(self):
        self.draft['cases'] = [dict(self.item, timeout_s=601)]
        self.write(self.root / 'draft.json', self.draft)
        self.seal['draft_sha256'] = digest(self.root / 'draft.json')
        self.reseal()
        with self.assertRaises(ValueError): self.check()

    def test_foreign_seal_or_draft_path_rejected(self):
        self.selection['sealed_precheck']['path'] = str(self.root / 'other.json')
        self.write(self.root / 'selection.json', self.selection)
        with self.assertRaises(ValueError): self.check()
        self.seal['draft'] = str(self.root / 'foreign.json')
        self.reseal()
        with self.assertRaises(ValueError): self.check()

    def test_install_delegates_without_changing_parent_entry(self):
        delegate = Mock(return_value='unrelated')
        parent = gate.original.checked.SCRIPT
        with patch.object(gate, '_HOOKS', None), \
             patch.object(gate.original, 'install_hooks'), \
             patch.object(gate.evidence, 'precheck', delegate):
            hooks = gate.install_hooks()
            self.assertIs(gate.install_hooks(), hooks)
            self.assertEqual(gate.original.checked.SCRIPT, parent)
            other, proof = {'name': 'app:other'}, object()
            self.assertEqual(gate.evidence.precheck(other, proof), 'unrelated')
            delegate.assert_called_once_with(other, proof)


class BatchTests(unittest.TestCase):
    def test_exact_registry_uses_sealed_adapter(self):
        with patch.object(batch.previous.previous, 'CATALOG', batch.CATALOG):
            names = batch.previous.previous.adapter_names([
                {'name': 'app:qbs_gap51_payload_matrix'},
                {'name': 'app:akv_gap54_skew_context'}])
            self.assertEqual(names, ['run_gap51_payload_checked_extension',
                                     'run_gap54_akv_sealed_extension'])
            with self.assertRaises(ValueError):
                batch.previous.previous.adapter_names([{'name': 'app:akv_gap54_other'}])

    def test_both_parent_admission_layers_retained(self):
        events = []
        inputs = Mock(files={str(batch.PREVIOUS): 'original'})
        inputs.pin.side_effect = lambda _: events.append('pin gap55')
        proof = Mock()
        proof.hashes.side_effect = lambda _: events.append('recheck gap55')

        def original_bind(validate):
            def wrapped(selection):
                events.append('original gap48 binding')
                return validate(selection)
            return wrapped

        def validate(selection):
            events.append('admit')
            return proof, ['row'], ['case']

        with patch.object(batch.previous.previous.evidence, 'Evidence', return_value=inputs):
            result = batch.bind_parent(validate, original_bind)('draft')
        self.assertEqual(result, (proof, ['row'], ['case']))
        self.assertEqual(events, ['pin gap55', 'original gap48 binding', 'admit', 'recheck gap55'])
        proof.hashes.assert_called_once_with({str(batch.PREVIOUS): 'original'})

    def test_parent_hash_drift_fails(self):
        proof = Mock()
        proof.hashes.side_effect = ValueError('parent drift')
        with patch.object(batch.previous.previous.evidence, 'Evidence'), self.assertRaises(ValueError):
            batch.bind_parent(lambda _: (proof, [], []), lambda validate: validate)('draft')


if __name__ == '__main__':
    unittest.main()
