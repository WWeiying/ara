import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_closure90_batch as batch


class Proof:
    def __init__(self, records):
        self.records = records
        self.files = {}

    def pin(self, path, expected=None):
        path = Path(path)
        self.files[str(path)] = expected or 'a' * 64
        return path

    def hashes(self, hashes):
        self.files.update(hashes)

    def read(self, path):
        self.pin(path)
        return copy.deepcopy(self.records[str(path)])


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.draft = self.root / 'draft.json'
        self.case = dict(name=next(iter(batch.CATALOG)), timeout_s=300)
        self.proof = Proof({str(self.draft): dict(cases=[self.case])})
        self.spec = dict(schema='closure90-batch-v1', baseline=str(batch.BASELINE),
            completion=str(batch.COMPLETION), baseline_bits=str(batch.BASELINE / 'combined-bits.json'),
            maximum_concurrent_workers=8, simulations_started=False,
            files={str(batch.SCRIPT): 'a' * 64, str(Path(batch.composer.__file__)): 'a' * 64,
                   str(self.draft): 'a' * 64}, drafts=[str(self.draft)], cases=[self.case])
        self.done = patch.object(batch, 'completed', return_value=dict(passed=651))
        self.done.start()
        self.addCleanup(self.done.stop)

    def check(self):
        batch.check_selection(self.spec, self.proof)

    def test_exact_bound_selection(self):
        self.check()

    def test_other_predecessor_rejected(self):
        self.spec['baseline'] = '/older650'
        with self.assertRaises(ValueError): self.check()

    def test_changed_case_rejected(self):
        self.spec['cases'] = [dict(self.case, timeout_s=301)]
        with self.assertRaises(ValueError): self.check()

    def test_resealed_over_budget_draft_rejected(self):
        self.case['timeout_s'] = 301
        with self.assertRaises(ValueError): self.check()

    def test_unknown_case_rejected(self):
        self.case['name'] = 'rvv:unreviewed'
        with self.assertRaises(ValueError): self.check()

    def test_unbound_draft_rejected(self):
        del self.spec['files'][str(self.draft)]
        with self.assertRaises(ValueError): self.check()

    def test_duplicate_drafts_rejected(self):
        self.spec['drafts'].append(str(self.draft))
        with self.assertRaises(ValueError): self.check()

    def test_unbound_adapter_rejected(self):
        del self.spec['files'][str(batch.SCRIPT)]
        with self.assertRaises(ValueError): self.check()

    def test_wrong_worker_budget_rejected(self):
        self.spec['maximum_concurrent_workers'] = 9
        with self.assertRaises(ValueError): self.check()

    def test_completed_requires_full_rehash(self):
        self.done.stop()
        self.done = patch.object(batch.closure_scorecard, 'scorecard', return_value=dict(
            passed=651, report_pins={'/report': 'a' * 64}))
        self.done.start()
        records = {str(batch.COMPLETION / 'completion.json'): dict(
            hash_stats=dict(unique_files=3, final_rehashed=2), files={})}
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            batch.completed(Proof(records))

    def trace_fixture(self):
        sim = self.root / 'simv'
        sim.write_bytes(b'small immutable image')
        config = dict(simv=str(sim), image={str(sim): batch.evidence.full.base.sha256(sim)},
                      results=str(self.root))
        cwd = self.root / 'case' / 'work'
        cwd.mkdir(parents=True)
        args = ['+TESTCASE=' + self.case['name'].split(':')[1], '+NO_FSDB']
        return config, args, cwd

    def test_vector_trace_added_without_changing_original_arguments(self):
        config, args, cwd = self.trace_fixture()
        command = batch.coverage_command(config, args, cwd)
        self.assertEqual(command[1:3], args)
        self.assertEqual(command[-1], '+VECTOR_TRACE=' + str(cwd / 'vector_trace.csv'))
        self.assertIn('-cm_dir', command)
        self.assertIn(str(cwd / 'code.vdb'), command)

    def test_vector_trace_override_rejected(self):
        config, args, cwd = self.trace_fixture()
        with self.assertRaisesRegex(ValueError, 'trace override'):
            batch.coverage_command(config, [*args, '+VECTOR_TRACE=/foreign'], cwd)

    def test_trace_foreign_case_rejected(self):
        config, args, cwd = self.trace_fixture()
        with self.assertRaisesRegex(ValueError, 'foreign closure'):
            batch.coverage_command(config, ['+TESTCASE=not_in_batch'], cwd)

    def test_trace_existing_vdb_rejected(self):
        config, args, cwd = self.trace_fixture()
        (cwd / 'code.vdb').mkdir()
        with self.assertRaises(ValueError):
            batch.coverage_command(config, args, cwd)


if __name__ == '__main__':
    unittest.main()
