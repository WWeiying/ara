"""Small isolated admission negatives; no simulator and no real-corpus mutation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_evidence as evidence
import run_gap49_payload_checked_extension as adapter
import compose_gap48_selection as composer
import analyze_gap49_payload as analysis


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SealTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='gap49-payload-test-', dir=ROOT / 'verification/out')
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.elf = self.out / 'toy.elf'
        self.tool = self.out / 'toy-compiler'
        self.elf.write_bytes(b'fixture-elf')
        self.tool.write_bytes(b'tool-A')
        self.record = self.out / 'toy.precheck.json'
        self.write(self.record, {'fixture_only': True})
        self.item = {'name': adapter.CASE, 'binary': str(self.elf), 'timeout_s': 600,
                     'sources': ['toy.c'], 'evidence': [str(self.record)],
                     'precheck': {'format': 'accel-host-v1', 'record': str(self.record)},
                     'rationale': 'fixture', 'targets': ['product'], 'source_audit': 'fixture'}
        self.result = {'name': adapter.CASE, 'status': 'PASS', 'scope': 'host-reference-only',
                       'elf_sha256': sha(self.elf), 'precheck': self.item['precheck']}
        self.draft = self.out / 'selection.checked-draft.json'
        self.write(self.draft, {'cases': [self.item]})
        for name in adapter.MANIFESTS:
            mapping = {str(self.tool): sha(self.tool)} if name == 'tool_hashes.json' else {
                str(self.elf): sha(self.elf)}
            self.write(self.out / name, mapping)
        proof = evidence.Evidence()
        proof.pin(self.draft)
        for name in adapter.MANIFESTS:
            proof.hashes(proof.read(self.out / name))
        self.delegate(self.item, proof)
        self.saved = {'status': 'PASS', 'scope': 'host-reference-only', 'read_only_validation': True,
                      'vcs_launched': False, 'checked_files': proof.files, 'result': copy.deepcopy(self.result)}
        self.reseal()

    def write(self, path, data):
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

    def delegate(self, item, proof):
        proof.pin(item['binary'], self.result['elf_sha256'])
        return copy.deepcopy(self.result)

    def reseal(self):
        saved_path = self.out / 'checked-precheck.json'
        self.write(saved_path, self.saved)
        self.write(self.out / 'draft.sha256.json', {str(p): sha(p) for p in
                   (self.draft, saved_path, self.out / 'artifact_hashes.json')})

    def run_gate(self, item=None):
        proof = evidence.Evidence()
        result = adapter.precheck(item or self.item, proof, self.delegate)
        return result, proof

    def test_exact_json_roundtrip_and_expanded_tools(self):
        item = json.loads(json.dumps(self.item, sort_keys=True))
        result, proof = self.run_gate(item)
        self.assertEqual(result, self.result)
        self.assertEqual(proof.files[str(self.tool)], sha(self.tool))
        self.assertIn(str(adapter.SCRIPT), proof.files)

    def test_case_fields_are_not_extended_by_composer(self):
        merged = composer.merge_cases([(self.draft, {'cases': [self.item]})], [], sha)
        self.assertEqual(merged, [self.item])
        self.run_gate(merged[0])

    def test_case_changes_including_extra_evidence_reject(self):
        for key, value in [('timeout_s', 601), ('sources', ['toy.c', 'parent.py']),
                           ('evidence', [str(self.record), 'parent.json']), ('rationale', 'changed')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_gate(dict(self.item, **{key: value}))

    def test_same_size_tool_edit_with_restored_mtime_rejects(self):
        before = self.tool.stat()
        self.tool.write_bytes(b'tool-B')
        os.utime(self.tool, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_elf_edit_rejects(self):
        self.elf.write_bytes(b'fixture-bad')
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_resealed_missing_or_extra_checked_file_rejects(self):
        original = copy.deepcopy(self.saved)
        for change in ('missing', 'extra'):
            with self.subTest(change=change):
                self.saved = copy.deepcopy(original)
                if change == 'missing':
                    del self.saved['checked_files'][str(self.tool)]
                else:
                    self.saved['checked_files']['unreviewed'] = 'a' * 64
                self.reseal()
                with self.assertRaises(ValueError):
                    self.run_gate()

    def test_resealed_changed_result_rejects(self):
        self.saved['result']['elf_sha256'] = 'a' * 64
        self.reseal()
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_false_scope_or_unchecked_saved_proof_rejects(self):
        original = copy.deepcopy(self.saved)
        for key, value in [('scope', 'RTL-PASS'), ('vcs_launched', True),
                           ('read_only_validation', False), ('status', 'PENDING')]:
            with self.subTest(key=key):
                self.saved = dict(original, **{key: value})
                self.reseal()
                with self.assertRaises(ValueError):
                    self.run_gate()

    def test_non_json_stable_result_rejects(self):
        self.result['integer_key'] = {0: 'not stable'}
        with self.assertRaisesRegex(ValueError, 'JSON stable'):
            self.run_gate()

    def test_wrong_seal_membership_rejects(self):
        path = self.out / 'draft.sha256.json'
        value = json.loads(path.read_text())
        del value[str(self.draft)]
        self.write(path, value)
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_symlink_retarget_rejects(self):
        self.tool.unlink()
        other = self.out / 'other-tool'
        other.write_bytes(b'tool-B')
        self.tool.symlink_to(other)
        with self.assertRaises(ValueError):
            self.run_gate()


class CompositionTests(unittest.TestCase):
    def test_install_is_idempotent_delegates_and_preserves_parent_script(self):
        delegate = Mock(return_value={'scope': 'other-case'})
        parent = Path('/parent/composer.py')
        with patch.object(adapter, '_HOOKS', None), \
                patch.object(evidence, 'precheck', delegate), \
                patch.object(adapter.checked, 'SCRIPT', parent):
            hook = adapter.install_hooks()
            self.assertIs(adapter.install_hooks(), hook)
            self.assertEqual(adapter.checked.SCRIPT, parent)
            item, proof = {'name': 'app:qbs_other'}, object()
            self.assertEqual(evidence.precheck(item, proof), {'scope': 'other-case'})
            delegate.assert_called_once_with(item, proof)
            self.assertIs(evidence.precheck.delegate, delegate)


class RoutingTests(unittest.TestCase):
    def test_minimum_and_selected_scope(self):
        result = analysis.analyze()
        self.assertEqual(result['reachable_points'], 52)
        self.assertEqual(result['minimum_stream_scenarios_in_supplied_universe'], 5)
        self.assertEqual(len(result['side_scenario']['point_ids']), 8)
        self.assertEqual(len(result['selected']['point_ids']), 16)
        selected = result['selected']
        self.assertEqual((selected['m'], selected['n'], selected['k_blocks'],
                          selected['custom_commands'], selected['timeout_s']), (1, 7, 1, 1, 600))
        self.assertEqual(selected['activation_access'], 'DIRECT')
        for bank in (0, 1):
            self.assertEqual(sorted(p['raw_index'] for p in result['points']
                                   if p['id'] in selected['point_ids'] and f'bank{bank}.' in p['scope']),
                             [145, 147, 149, 151, 153, 155, 217, 219])


if __name__ == '__main__':
    unittest.main()
