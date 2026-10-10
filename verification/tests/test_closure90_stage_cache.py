"""Exercise closure wrappers with real small SHA sessions, without EDA."""
from collections import Counter
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_closure90_batch as batch
import coverage_hash_session as hashes


class StageCacheTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.output = self.root / 'new-output'
        self.completion = self.root / 'receipt'
        self.completion.mkdir()
        self.baseline = self.root / 'baseline'
        self.test_vdb = self.baseline / 'results/historical/code.vdb'
        self.design_vdb = self.baseline / 'design.vdb'
        for database in (self.test_vdb, self.design_vdb):
            database.mkdir(parents=True)
            (database / 'data.xml').write_bytes(b'small immutable VDB member')
        self.save(self.baseline / 'all-passed-outcomes.json', [dict(vdb=str(self.test_vdb))])
        self.save(self.baseline / 'plan.json', dict(design_vdb=str(self.design_vdb)))
        self.source = self.make_input('historic.log', b'strict historical evidence')
        self.selected = self.make_input('selected.log', b'selected evidence')
        self.case_source = self.make_input('case.c', b'selected source')
        self.binary = self.make_input('case.elf', b'selected binary')
        self.draft = self.make_input('draft.json', b'{}')
        self.helper = self.make_input('cache_helper.py', b'fixture helper source')
        self.adapter = ModuleType('small_stage_adapter')
        self.adapter.__file__ = str(self.make_input('adapter.py', b'fixture adapter source'))
        self.adapter.sha = hashes.RAW_SHA256
        self.adapter.digest = hashes.RAW_BITMAP_DIGEST
        self.spec = dict(files=batch.evidence.full.pins([self.draft]), cases=[dict(
            name='fixture', sources=[str(self.case_source)], evidence=[str(self.selected)],
            binary=str(self.binary))])
        self.save(self.completion / 'completion.json', dict(files=batch.evidence.full.pins([
            self.source, self.baseline / 'all-passed-outcomes.json', self.baseline / 'plan.json'])))
        self.save(self.completion / 'checkpoint.json', dict(status='PASS', coverage_status='COMPLETE'))
        self.selection = self.root / 'selection.json'
        self.save(self.selection, self.spec)
        self.stack.enter_context(patch.object(batch, 'BASELINE', self.baseline))
        self.stack.enter_context(patch.object(batch, 'COMPLETION', self.completion))
        original_read = batch.evidence.full.read
        def sandbox_read(path):
            if not Path(path).resolve().is_relative_to(self.root):
                raise AssertionError(f'fixture attempted non-sandbox JSON read: {path}')
            return original_read(path)
        self.stack.enter_context(patch.object(batch.evidence.full, 'read', side_effect=sandbox_read))
        self.stack.enter_context(patch.object(hashes, '__file__', str(self.helper)))
        self.stack.enter_context(patch.object(hashes, 'verification_modules',
                                             return_value=[self.adapter, batch.evidence.full.base]))
        self.prepare = self.stack.enter_context(patch.object(batch.checked, 'prepare', side_effect=self.prepare_fixture))
        self.summarize = self.stack.enter_context(patch.object(batch.checked, 'summarize', side_effect=self.summarize_fixture))
        self.frozen = self.stack.enter_context(patch.object(batch.checked, 'frozen',
                                                           side_effect=AssertionError('no extra full frozen pass')))
        self.failure = self.stack.enter_context(patch.object(batch.checked, 'failure', wraps=batch.checked.failure))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.sessions = []
        self.reads = Counter()
        original = hashes.HashSession

        def make_session(*, hasher):
            def measured(path):
                self.reads[path] += 1
                return hasher(path)
            session = original(hasher=measured)
            self.sessions.append(session)
            return session

        self.stack.enter_context(patch.object(hashes, 'HashSession', side_effect=make_session))
        self.invoke = batch.evidence.full.batch.invoke
        self.popen = subprocess.Popen
        self.result = [dict(name='fixture', status='PASS')]
        batch.install_stage_cache(self.spec)

    def make_input(self, name, value):
        path = self.inputs / name
        path.write_bytes(value)
        return path

    def save(self, path, value):
        batch.evidence.full.save(path, value)

    def read(self, path):
        return batch.evidence.full.read(path)

    def assert_scope_active(self):
        self.assertIsNotNone(hashes._active)
        self.assertFalse(hashes._active.finished)
        self.assertIs(batch.evidence.full.batch.invoke, self.invoke)
        self.assertIs(subprocess.Popen, self.popen)

    def read_shared_input(self):
        a = self.adapter.sha(self.source)
        self.assertEqual(self.adapter.digest(self.source), a)
        self.assertEqual(self.adapter.sha(self.source), a)

    def prepare_fixture(self, output, selection):
        self.assert_scope_active()
        self.assertEqual(selection, self.selection)
        output.mkdir()
        self.read_shared_input()
        writable = output / 'generated.json'
        writable.write_bytes(b'before rewrite')
        before = self.adapter.sha(writable)
        writable.write_bytes(b'after rewrite')
        self.assertNotEqual(self.adapter.sha(writable), before)
        self.prepared = dict(cases=[dict(name='fixture', timeout_s=300)],
                             checked_extension='checked-extension-v1',
                             source_selection=dict(selection=str(selection)),
                             files=batch.evidence.full.pins([self.source, self.helper, writable, selection]))
        self.save(output / 'plan.json', self.prepared)
        self.save(output / 'plan.sha256.json', batch.evidence.full.pins([output / 'plan.json']))
        self.save(output / 'checkpoint.json', dict(status='PREPARED', phase='prepared', coverage_status='PENDING'))
        self.assertFalse((output / 'prepare-hash-session.json').exists())

    def summarize_fixture(self, output, plan):
        self.assert_scope_active()
        self.read_shared_input()
        self.save(output / 'collection.json', dict(status='PASS', passed=652))
        self.assertFalse((output / 'summarize-hash-session.json').exists())
        self.assertNotEqual(self.read(output / 'checkpoint.json')['coverage_status'], 'COMPLETE')
        return self.result

    def prepare_output(self):
        batch.checked.prepare(self.output, self.selection)
        self.frozen.assert_not_called()

    def assert_prepare_rejected(self):
        self.assertFalse((self.output / 'prepare-hash-session.json').exists())
        self.assertEqual(self.read(self.output / 'checked-failure.json')['status'], 'REJECTED')
        self.assertEqual(self.read(self.output / 'checkpoint.json')['status'], 'PREFLIGHT_FAILED')
        self.assertIsNone(hashes._active)
        self.failure.assert_called_once()

    def test_prepare_real_cache_and_final_rehash_keep_original_plan(self):
        self.prepare_output()
        self.assertEqual(self.reads[self.source], 2)
        self.assertIsNone(hashes._active)
        report = self.read(self.output / 'prepare-hash-session.json')
        self.assertTrue(report['finished'])
        self.assertEqual(report['unique_files'], report['final_rehashed'])
        self.assertGreaterEqual(report['cache_hits'], 2)
        final = self.read(self.output / 'plan.json')
        self.assertEqual({k: v for k, v in final.items() if k != 'files'},
                         {k: v for k, v in self.prepared.items() if k != 'files'})
        for path, digest in self.prepared['files'].items():
            self.assertEqual(final['files'][path], digest)
        batch.evidence.full.check(final['files'])
        batch.evidence.full.check(self.read(self.output / 'plan.sha256.json'))
        self.failure.assert_not_called()

    def test_existing_output_guard_preserves_every_byte_without_roots_or_failure(self):
        self.output.mkdir()
        self.save(self.output / 'checkpoint.json', dict(status='PASS', phase='complete', coverage_status='COMPLETE'))
        sentinel = self.output / 'plan.json'
        sentinel.write_bytes(b'existing sealed plan')
        original = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with patch.object(batch, 'immutable_inputs', wraps=batch.immutable_inputs) as roots:
            with self.assertRaisesRegex(ValueError, 'new output directory required'):
                batch.checked.prepare(self.output, self.selection)
            roots.assert_not_called()
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, original)
        self.prepare.assert_not_called()
        self.failure.assert_not_called()

    def test_prepare_stage_error_preserved_and_records_failure(self):
        self.prepare.side_effect = RuntimeError('original oracle rejection')
        with self.assertRaisesRegex(RuntimeError, 'original oracle rejection'):
            batch.checked.prepare(self.output, self.selection)
        self.assert_prepare_rejected()

    def test_missing_immutable_input_records_prepare_failure(self):
        self.spec['cases'][0]['evidence'].append(str(self.inputs / 'missing'))
        with self.assertRaisesRegex(ValueError, 'immutable input is not a file'):
            batch.checked.prepare(self.output, self.selection)
        self.assert_prepare_rejected()
        self.prepare.assert_not_called()

    def test_final_rehash_failure_blocks_prepare_report_and_records_failure(self):
        original = self.prepare_fixture
        def stage(output, selection):
            original(output, selection)
            def fail(path):
                raise ValueError('uncached final rehash failed')
            hashes._active.hashes.hasher = fail
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'uncached final rehash failed'):
            batch.checked.prepare(self.output, self.selection)
        self.assert_prepare_rejected()

    def test_input_mutation_after_stage_blocks_prepare_publication(self):
        def stage(output, selection):
            self.prepare_fixture(output, selection)
            self.source.write_bytes(b'tampered evidence')
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            batch.checked.prepare(self.output, self.selection)
        self.assert_prepare_rejected()

    def test_exact_roots_include_selected_and_loaded_files_exclude_output_aliases(self):
        self.output.mkdir()
        generated = self.output / 'writable'
        generated.write_bytes(b'generated')
        alias = self.inputs / 'output-alias'
        alias.symlink_to(generated)
        plan = dict(files=batch.evidence.full.pins([generated, alias]))
        roots = set(batch.immutable_inputs(self.spec, self.output, plan))
        expected = {self.source, self.draft, self.case_source, self.selected, self.binary,
                    self.completion / 'completion.json', self.completion / 'checkpoint.json',
                    self.baseline / 'all-passed-outcomes.json', self.baseline / 'plan.json',
                    Path(self.adapter.__file__), Path(batch.evidence.full.base.__file__)}
        self.assertEqual({p for p in roots if p.is_file()}, expected)
        self.assertEqual({p for p in roots if p.is_dir()}, {self.test_vdb, self.design_vdb})
        self.assertEqual(roots, expected | {self.test_vdb, self.design_vdb})
        with hashes.scoped_hashes(self.output, immutable_roots=roots, modules=[]) as session:
            self.assertEqual(set(session.directory_targets), {self.test_vdb, self.design_vdb})
            self.assertEqual(set(session.snapshots[self.test_vdb]),
                             {str(self.test_vdb), str(self.test_vdb / 'data.xml')})
            self.assertEqual(set(session.snapshots[self.design_vdb]),
                             {str(self.design_vdb), str(self.design_vdb / 'data.xml')})
        self.assertNotIn(generated, roots)
        self.assertNotIn(alias, roots)

    def test_vdb_member_added_during_prepare_final_rehash_blocks_publication(self):
        original = self.prepare_fixture
        def stage(output, selection):
            original(output, selection)
            hasher = hashes._active.hashes.hasher
            def add_member(path):
                digest = hasher(path)
                (self.test_vdb / 'unexpected.xml').write_bytes(b'added during final rehash')
                return digest
            hashes._active.hashes.hasher = add_member
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            batch.checked.prepare(self.output, self.selection)
        self.assert_prepare_rejected()

    def test_design_vdb_member_removed_during_summary_final_rehash_blocks_return(self):
        self.prepare_output()
        original = self.summarize_fixture
        def stage(output, plan):
            result = original(output, plan)
            hasher = hashes._active.hashes.hasher
            def remove_member(path):
                digest = hasher(path)
                (self.design_vdb / 'data.xml').unlink(missing_ok=True)
                return digest
            hashes._active.hashes.hasher = remove_member
            return result
        self.summarize.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            batch.checked.summarize(self.output, self.read(self.output / 'plan.json'))
        self.assertFalse((self.output / 'summarize-hash-session.json').exists())
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'PENDING')
        self.assertIsNone(hashes._active)

    def test_post_rehash_semantics_or_old_pin_drift_rejected(self):
        finish = hashes.CoverageHashSession.finish
        def change(session):
            finish(session)
            plan = self.read(self.output / 'plan.json')
            plan['cases'][0]['timeout_s'] = 301
            self.save(self.output / 'plan.json', plan)
        with patch.object(hashes.CoverageHashSession, 'finish', change):
            with self.assertRaisesRegex(ValueError, 'plan semantics changed'):
                batch.checked.prepare(self.output, self.selection)
        self.failure.assert_called_once()
        self.assertEqual(self.read(self.output / 'checkpoint.json')['status'], 'PREFLIGHT_FAILED')

    def test_post_rehash_old_input_pin_drift_rejected(self):
        finish = hashes.CoverageHashSession.finish
        def change(session):
            finish(session)
            plan = self.read(self.output / 'plan.json')
            plan['files'][str(self.source)] = '0' * 64
            self.save(self.output / 'plan.json', plan)
        with patch.object(hashes.CoverageHashSession, 'finish', change):
            with self.assertRaisesRegex(ValueError, 'prepared input pin changed'):
                batch.checked.prepare(self.output, self.selection)
        self.failure.assert_called_once()

    def test_small_file_change_after_expected_hash_capture_rejected(self):
        check = batch.evidence.full.check
        def change_then_check(files):
            report = self.output / 'prepare-hash-session.json'
            if hashes._active is None and str(report) in files:
                report.write_bytes(b'changed after expected hash capture')
            return check(files)
        with patch.object(batch.evidence.full, 'check', side_effect=change_then_check):
            with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
                batch.checked.prepare(self.output, self.selection)
        self.failure.assert_called_once()

    def test_sealed_report_drift_before_small_check_must_not_be_resealed(self):
        save = batch.evidence.full.save
        def change_after_seal(path, value):
            save(path, value)
            if hashes._active is None and path == self.output / 'plan.sha256.json':
                report = self.output / 'prepare-hash-session.json'
                altered = self.read(report)
                altered['status'] = 'TAMPERED_AFTER_SEAL'
                save(report, altered)
        with patch.object(batch.evidence.full, 'save', side_effect=change_after_seal):
            with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
                batch.checked.prepare(self.output, self.selection)
        self.failure.assert_called_once()

    def test_summarize_return_and_parent_completion_follow_real_final_rehash(self):
        self.prepare_output()
        plan = self.read(self.output / 'plan.json')
        initial_reads = self.reads[self.source]
        result = batch.checked.summarize(self.output, plan)
        self.assertIs(result, self.result)
        self.assertIsNone(hashes._active)
        self.assertEqual(self.reads[self.source] - initial_reads, 2)
        report = self.read(self.output / 'summarize-hash-session.json')
        self.assertTrue(report['finished'])
        self.assertEqual(report['unique_files'], report['final_rehashed'])
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'PENDING')
        self.save(self.output / 'checkpoint.json', dict(status='PASS', phase='complete', coverage_status='COMPLETE'))
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'COMPLETE')

    def test_final_rehash_failure_does_not_return_summary_or_publish_complete(self):
        self.prepare_output()
        plan = self.read(self.output / 'plan.json')
        original = self.summarize_fixture
        def stage(output, current):
            result = original(output, current)
            def fail(path):
                raise ValueError('summary final rehash failed')
            hashes._active.hashes.hasher = fail
            return result
        self.summarize.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'summary final rehash failed'):
            batch.checked.summarize(self.output, plan)
        self.assertFalse((self.output / 'summarize-hash-session.json').exists())
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'PENDING')
        self.assertIsNone(hashes._active)

    def test_summary_error_preserved_without_completion(self):
        self.prepare_output()
        self.summarize.side_effect = RuntimeError('actual summarize failure')
        with self.assertRaisesRegex(RuntimeError, 'actual summarize failure'):
            batch.checked.summarize(self.output, self.read(self.output / 'plan.json'))
        self.assertFalse((self.output / 'summarize-hash-session.json').exists())
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'PENDING')
        self.assertIsNone(hashes._active)


if __name__ == '__main__':
    unittest.main()
