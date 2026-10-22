"""Focused regression tests for the standalone FPU current-output audit."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import audit_pending_fpu_20261016 as audit


def example():
    scalar = 1
    require(scalar == 1, 'exact scalar')
    for i in range(2):
        require(i < 2, 'exact loop')
    forbidden = 'not executed'


class PendingFpuAuditTests(unittest.TestCase):
    def test_scope_is_exact_and_disjoint(self):
        ledger = json.loads((audit.ROOT / 'verification/out/full-regression-reviewed-20261015-01/case-ledger.json').read_text())
        import re
        expected = {r['index'] for r in ledger['cases'] if r['status'] == 'CHECKER_REQUIRED'
                    and re.search('div|sqrt|red32|midmant|fpu|ured|c910_float|fclass', r['coverage_test'])
                    and not re.search('qbs|akv|vpure_war_div_indexed_load', r['coverage_test'])}
        self.assertEqual(set(audit.CASES), expected)
        self.assertEqual(len(audit.CASES), 35)

    def test_source_block_preserves_nested_predicates_only(self):
        tree, source = audit.source_block(example, 'scalar =', 'forbidden =')
        namespace = {'require': audit.require}
        exec(compile(tree, '<test>', 'exec'), namespace)
        self.assertEqual(namespace['scalar'], 1)
        self.assertNotIn('forbidden', namespace)
        self.assertIn("require(i < 2, 'exact loop')", source)

    def test_missing_boundary_fails_closed(self):
        with self.assertRaises(ValueError):
            audit.source_block(example, 'scalar =', 'missing =')

    def test_view_retains_actual_traces_but_routes_derived_files(self):
        a = SimpleNamespace(work=Path('/raw/work'), out=Path('/fresh'))
        view = audit.CurrentView(a)
        self.assertEqual(view / 'commit_trace.csv', Path('/raw/work/commit_trace.csv'))
        self.assertEqual(view / 'run.vcs.log', Path('/fresh/runtime/run.vcs.log'))
        self.assertEqual(view / 'epoch1', Path('/fresh/epoch1'))

    def test_numerical_mismatch_is_fail_adapter_is_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            a = SimpleNamespace(out=Path(directory))
            self.assertEqual(audit.classify_error(a, ValueError('schema')), 'CHECKER_REQUIRED')
            self.assertEqual(audit.classify_error(a, ValueError('Full VRF differs')), 'FAIL')
            (a.out / 'scalar.json').write_text(json.dumps({'mismatch': {'pc': '0x80000000'}}))
            self.assertEqual(audit.classify_error(a, ValueError('gold')), 'FAIL')

    def test_original_arithmetic_predicates_exclude_coverage_union(self):
        import importlib
        for gap in range(83, 89):
            module = importlib.import_module('admit_gap%d_offline' % gap)
            tree, source = audit.source_block(module.main, 'scalar =', 'check()')
            self.assertIn('compare_commit_prefix', source)
            self.assertIn('compare_vector_commits', source)
            self.assertTrue('writes.get' in source or 'check_signature(writes)' in source)
            self.assertNotIn('bitmap.collect', source)
            self.assertNotIn('simulation-status.json', source)
            self.assertNotIn('base /', source)
        self.assertIn(744, audit.RESET_CASES)
        self.assertNotIn(783, audit.RESET_CASES)

    def test_original_gap95_rejects_numeric_and_signature_mutations(self):
        import admit_gap95_batch as q
        spec = dict(expected_vector_instructions=48, expected_vector_bytes=12288,
                    checks=1616, symbols=dict(g75_result=0x100, num_failed=0x200, tohost=0x300))
        vector = dict(status='PASS', compared_instructions=48, compared_bytes=12288,
                      skipped_unknown_bytes=0, non_bit_exact_instructions=0,
                      incomplete_requests=[], unretired_requests=[], trapped_requests=[])
        self.assertTrue(q.vector_exact(vector, spec))
        self.assertFalse(q.vector_exact(dict(vector, compared_bytes=12287), spec))
        self.assertFalse(q.vector_exact(dict(vector, non_bit_exact_instructions=1), spec))
        writes = {0x100: (0x0f, 1616), 0x104: (0xf0, 0), 0x200: (0x0f, 0), 0x300: (0xff, 1)}
        self.assertTrue(q.signature_exact(writes, spec))
        self.assertFalse(q.signature_exact(writes | {0x104: (0xf0, 1)}, spec))

    def test_original_literal_specs_are_read_without_wrapper_side_effects(self):
        a = SimpleNamespace(bind=lambda path: path)
        for gap, instructions, checks in ((91, 60, 1320), (92, 24, 528), (93, 24, 272),
                                         (94, 30, 660), (96, 42, 2758)):
            spec = audit.literal_spec(a, gap)
            self.assertEqual(spec['instructions'], instructions)
            self.assertEqual(spec['checks'], checks)

    def test_red32_rejects_prefix_skips_unknowns_and_population_mutations(self):
        exact = dict(status='PASS', stopped_at_spike_index=None, first_mismatch=None,
            vector_destination_requests=84, prefix_vector_destination_requests=84,
            compared_instructions=84, compared_bytes=19908, skipped_unknown_bytes=0,
            non_bit_exact_instructions=0, unobservable_instructions=0,
            incomplete_requests=[], unretired_requests=[], trapped_requests=[],
            instructions=[dict(unknown_write_bytes=0, skipped_unknown_bytes=0, mismatch_count=0)])
        audit.red32_vector_gate(exact)
        for key, value in (('stopped_at_spike_index', 2), ('compared_instructions', 83),
                           ('compared_bytes', 19796), ('skipped_unknown_bytes', 112),
                           ('non_bit_exact_instructions', 14), ('unobservable_instructions', 1),
                           ('unretired_requests', [9]), ('incomplete_requests', [9]),
                           ('trapped_requests', [9])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit.red32_vector_gate(exact | {key: value})
        with self.assertRaises(ValueError):
            audit.red32_vector_gate(exact | {'instructions': [dict(unknown_write_bytes=1,
                skipped_unknown_bytes=0, mismatch_count=0)]})

    def test_ured_current_cycle_adaptation_preserves_all_other_predicates(self):
        import ast
        import inspect
        import textwrap
        import postprocess_vmfpu_ured_reset763 as q
        _, source = audit.cancelled_binding_current(q.cancelled_binding, 6504, {})
        original = ast.parse(textwrap.dedent(inspect.getsource(q.cancelled_binding)))
        modified = ast.parse(source)
        for node in ast.walk(modified):
            if isinstance(node, ast.Constant) and node.value == 6504:
                node.value = 8568
        self.assertEqual(ast.dump(original), ast.dump(modified))
        self.assertIn('8568', inspect.getsource(q.cancelled_binding))

    def test_epoch_validator_rejects_undeclared_second_reset(self):
        from qualify_gap113_cached_reset import split_epochs
        commits = [dict(cycle=str(c), event='retire', order=str(o), trap='0')
                   for c, o in ((5, 0), (6, 1), (1, 0), (2, 1))]
        vectors = [dict(event='config', cycle='0'), dict(event='reset', cycle='7')]
        epochs, cut = split_epochs(commits, vectors)
        self.assertEqual(cut, 7)
        self.assertEqual(len(epochs), 2)
        with self.assertRaises(ValueError):
            split_epochs(commits, vectors + [dict(event='reset', cycle='8')])


if __name__ == '__main__':
    unittest.main()
