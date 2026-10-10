"""Gap51 isolated routing/admission negatives, without simulator or corpus edits."""
import copy
import hashlib
import importlib.util
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
import run_gap51_payload_checked_extension as adapter
import compose_gap48_selection as composer
import analyze_gap51_payload as analysis
import build_gap51_payload as builder


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SealTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='gap51-payload-test-', dir=ROOT / 'verification/out')
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.elf, self.tool = self.out / 'toy.elf', self.out / 'toy-compiler'
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
        self.saved = dict(status='PASS', scope='host-reference-only', read_only_validation=True,
                          vcs_launched=False, checked_files=proof.files, result=copy.deepcopy(self.result))
        self.reseal()

    def write(self, path, data):
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

    def delegate(self, item, proof):
        proof.pin(item['binary'], self.result['elf_sha256'])
        return copy.deepcopy(self.result)

    def reseal(self):
        path = self.out / 'checked-precheck.json'
        self.write(path, self.saved)
        self.write(self.out / 'draft.sha256.json', {str(p): sha(p) for p in
                   (self.draft, path, self.out / 'artifact_hashes.json')})

    def run_gate(self, item=None):
        proof = evidence.Evidence()
        result = adapter.precheck(item or self.item, proof, self.delegate)
        return result, proof

    def test_json_roundtrip_and_tool_binding(self):
        result, proof = self.run_gate(json.loads(json.dumps(self.item)))
        self.assertEqual(result, self.result)
        self.assertEqual(proof.files[str(self.tool)], sha(self.tool))
        self.assertIn(str(adapter.SCRIPT), proof.files)

    def test_composer_preserves_case_exactly(self):
        merged = composer.merge_cases([(self.draft, {'cases': [self.item]})], [], sha)
        self.assertEqual(merged, [self.item])
        self.run_gate(merged[0])

    def test_case_changes_rejected(self):
        for key, value in [('timeout_s', 601), ('sources', ['toy.c', 'parent.py']),
                           ('evidence', [str(self.record), 'parent.json']), ('rationale', 'changed')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_gate(dict(self.item, **{key: value}))

    def test_same_size_tool_edit_with_restored_mtime_rejected(self):
        before = self.tool.stat()
        self.tool.write_bytes(b'tool-B')
        os.utime(self.tool, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_elf_edit_rejected(self):
        self.elf.write_bytes(b'fixture-bad')
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_missing_or_extra_checked_file_rejected(self):
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

    def test_changed_result_rejected(self):
        self.saved['result']['elf_sha256'] = 'a' * 64
        self.reseal()
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_wrong_scope_or_unchecked_proof_rejected(self):
        original = copy.deepcopy(self.saved)
        for key, value in [('scope', 'RTL-PASS'), ('vcs_launched', True),
                           ('read_only_validation', False), ('status', 'PENDING')]:
            with self.subTest(key=key):
                self.saved = dict(original, **{key: value})
                self.reseal()
                with self.assertRaises(ValueError):
                    self.run_gate()

    def test_non_json_stable_result_rejected(self):
        self.result['integer_key'] = {0: 'not stable'}
        with self.assertRaisesRegex(ValueError, 'JSON stable'):
            self.run_gate()

    def test_wrong_seal_membership_rejected(self):
        path = self.out / 'draft.sha256.json'
        value = json.loads(path.read_text())
        del value[str(self.draft)]
        self.write(path, value)
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_symlink_retarget_rejected(self):
        self.tool.unlink()
        other = self.out / 'other-tool'
        other.write_bytes(b'tool-B')
        self.tool.symlink_to(other)
        with self.assertRaises(ValueError):
            self.run_gate()


class CompositionTests(unittest.TestCase):
    def test_install_delegates_and_preserves_parent_script(self):
        delegate = Mock(return_value={'scope': 'other-case'})
        parent = Path('/parent/composer.py')
        with patch.object(adapter, '_HOOKS', None), patch.object(evidence, 'precheck', delegate), \
                patch.object(adapter.checked, 'SCRIPT', parent):
            hooks = adapter.install_hooks()
            self.assertIs(adapter.install_hooks(), hooks)
            self.assertEqual(adapter.checked.SCRIPT, parent)
            item, proof = {'name': 'app:qbs_other'}, object()
            self.assertEqual(evidence.precheck(item, proof), {'scope': 'other-case'})
            delegate.assert_called_once_with(item, proof)
            self.assertIs(evidence.precheck.delegate, delegate)

    def test_install_dispatches_only_own_case(self):
        delegate = Mock(return_value={'scope': 'other-case'})
        with patch.object(adapter, '_HOOKS', None), patch.object(evidence, 'precheck', delegate), \
                patch.object(adapter, 'precheck', return_value={'scope': 'host-reference-only'}) as gate:
            adapter.install_hooks()
            item, proof = {'name': adapter.CASE}, object()
            self.assertEqual(evidence.precheck(item, proof), {'scope': 'host-reference-only'})
            gate.assert_called_once_with(item, proof, delegate)
            delegate.assert_not_called()


class RoutingTests(unittest.TestCase):
    def test_exact_remaining_points_and_minimal_shapes(self):
        result = analysis.analyze()
        prior, remaining = set(result['prior_gap49_target_ids']), set(result['remaining_target_ids'])
        self.assertEqual(len(prior), 16)
        self.assertEqual(len(remaining), 36)
        self.assertFalse(prior & remaining)
        self.assertEqual(prior | remaining, set(range(52)))
        self.assertEqual(result['custom_commands'], 4)
        self.assertEqual(result['active_outputs'], 28)
        self.assertEqual(result['total_weight_bytes'], 1200)
        self.assertEqual(result['total_activation_bytes'], 4964)
        self.assertEqual([len(c['target_ids']) for c in result['commands']], [12, 8, 12, 4])
        expected_raw = [list(range(449, 472, 2)), list(range(393, 408, 2)),
                        [337, 339, 341, 343, 1495, 1498, 1663, 1666, 1831, 1834, 1999, 2002],
                        [257, 321, 385, 449]]
        for c, raw in zip(result['commands'], expected_raw):
            self.assertEqual(sorted(result['points'][i]['raw_index'] for i in c['target_ids']), raw)
            self.assertEqual(c['k_blocks'], 1)
            self.assertEqual(c['w_mod16'], 0)
            self.assertEqual(c['activation_access'], 'DIRECT')

    def test_deleting_each_command_leaves_a_gap(self):
        result = analysis.analyze()
        commands = result['commands']
        for omitted in range(4):
            covered = set().union(*(set(c['target_ids']) for i, c in enumerate(commands) if i != omitted))
            self.assertNotEqual(covered, set(result['remaining_target_ids']))

    def test_n4_cannot_reach_bank1_side_metadata(self):
        spec = importlib.util.spec_from_file_location('routing_fixture', analysis.HISTORY / 'payload_analysis.py')
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        command = dict(analysis.COMMANDS[2], n=4)
        _, side = analysis.command_routes(model, command, 1)
        self.assertEqual(side, set())

    def test_oracle_header_rejects_shape_and_scope_mutations(self):
        result = analysis.analyze()
        commands = result['commands']
        slices = [(bytes(c['weight_bytes']), None, None) for c in commands]
        oracles = [dict(activation_hex=bytes(c['activation_bytes']).hex(), expected_bits=[0] * (c['m'] * c['n']),
                        scope='host-reference-only', custom_instruction_execution_prechecked=False,
                        independent_native_decode=True, m8_padding_checked=c['m'] == 5, fflags=1) for c in commands]
        with tempfile.TemporaryDirectory(prefix='gap51-payload-test-', dir=ROOT / 'verification/out') as temp:
            for key, value in [('scope', 'RTL-PASS'), ('expected_bits', [0]), ('activation_hex', '00'),
                               ('fflags', 32), ('independent_native_decode', False)]:
                corrupted = copy.deepcopy(oracles)
                corrupted[0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    builder.emit_header(Path(temp), commands, slices, corrupted)


if __name__ == '__main__':
    unittest.main()
