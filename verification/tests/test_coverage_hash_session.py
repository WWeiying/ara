from contextlib import ExitStack, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import coverage_hash_session as h
import recover_gap65_report_only as recovery
from ara_verify import artifacts


class HashScopeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.inputs, self.output = self.root / 'inputs', self.root / 'output'
        self.inputs.mkdir()
        self.output.mkdir()
        self.source = self.inputs / 'data'
        self.source.write_bytes(b'original')
        self.generated = self.output / 'plan.json'
        self.generated.write_bytes(b'first plan')
        self.aliases = ModuleType('collector_aliases')
        self.aliases.sha = h.RAW_SHA256
        self.aliases.digest = h.RAW_BITMAP_DIGEST
        self.aliases.RAW_SHA256 = h.RAW_SHA256
        self.stack.enter_context(redirect_stdout(io.StringIO()))

    def scope(self, roots=None, modules=None):
        return h.scoped_hashes(self.output, immutable_roots=roots or [self.inputs],
                               modules=[self.aliases] if modules is None else modules)

    def test_two_aliases_share_one_initial_read_and_uncached_final_rehash(self):
        with self.scope() as session:
            hasher = Mock(wraps=h.RAW_SHA256)
            session.hashes.hasher = hasher
            a = self.aliases.sha(self.source)
            self.assertEqual(self.aliases.digest(self.source), a)
            self.assertEqual(self.aliases.sha(self.source), a)
            self.assertEqual(hasher.call_count, 1)
            self.assertIs(self.aliases.RAW_SHA256, h.RAW_SHA256)
        self.assertEqual(hasher.call_count, 2)
        self.assertEqual(session.stats()['cache_hits'], 2)
        self.assertEqual(session.stats()['final_rehashed'], 1)
        self.assertTrue(session.finished)
        self.assertIs(self.aliases.sha, h.RAW_SHA256)
        self.assertIs(self.aliases.digest, h.RAW_BITMAP_DIGEST)

    def test_output_changes_always_raw_and_never_cached(self):
        with self.scope() as session, patch.object(h, 'RAW_SHA256', wraps=h.RAW_SHA256) as raw:
            a = self.aliases.sha(self.generated)
            self.generated.write_bytes(b'second plan')
            b = self.aliases.digest(self.generated)
            self.assertNotEqual(a, b)
            self.assertEqual(raw.call_count, 2)
            self.assertEqual(session.hashes.entries, {})
        self.assertEqual(session.stats()['uncached_reads'], 2)

    def test_undeclared_file_raw_not_cached(self):
        other = self.root / 'not-declared'
        other.write_bytes(b'a')
        with self.scope() as session:
            a = self.aliases.sha(other)
            other.write_bytes(b'b')
            self.assertNotEqual(a, self.aliases.sha(other))
        self.assertEqual(session.hashes.entries, {})

    def test_symlink_into_output_is_raw(self):
        link = self.inputs / 'output-link'
        link.symlink_to(self.generated)
        with self.scope() as session:
            a = self.aliases.sha(link)
            self.generated.write_bytes(b'rewritten plan')
            self.assertNotEqual(a, self.aliases.digest(link))
        self.assertEqual(session.hashes.entries, {})

    def test_symlink_alias_into_immutable_input_is_cached_and_bound(self):
        link = self.root / 'input-alias'
        link.symlink_to(self.source)
        with self.scope() as session:
            self.aliases.sha(link)
            self.aliases.digest(link)
        self.assertEqual(session.stats()['unique_files'], 1)
        self.assertEqual(session.stats()['cache_hits'], 1)

    def test_output_symlink_exclusion(self):
        alias_output = self.root / 'output-alias'
        alias_output.symlink_to(self.output, target_is_directory=True)
        with h.scoped_hashes(alias_output, immutable_roots=[self.inputs], modules=[self.aliases]) as session:
            self.aliases.sha(self.generated)
            self.aliases.sha(alias_output / self.generated.name)
            self.generated.write_bytes(b'allowed output mutation')
        self.assertEqual(session.hashes.entries, {})

    def test_lexical_dotdot_into_output_is_raw(self):
        with self.scope() as session:
            self.aliases.sha(self.inputs / '..' / 'output' / self.generated.name)
        self.assertEqual(session.hashes.entries, {})

    def test_same_size_restored_mtime_mutation_rejected_on_reuse(self):
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            with self.scope():
                self.aliases.sha(self.source)
                before = self.source.stat()
                self.source.write_bytes(b'tampered')
                os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.aliases.sha(self.source)
        self.assertIs(self.aliases.sha, h.RAW_SHA256)

    def test_final_rehash_does_not_trust_unchanged_stat(self):
        with self.assertRaisesRegex(ValueError, 'during final rehash'):
            with self.scope() as session:
                self.aliases.sha(self.source)
                bound = recovery.identity(self.source)
                snapshots = session.snapshots
                self.source.write_bytes(b'tampered')
                self.stack.enter_context(patch.object(recovery, 'identity', return_value=bound))
                self.stack.enter_context(patch.object(h, 'tree_snapshot', side_effect=snapshots.__getitem__))

    def test_added_file_without_hash_call_rejected(self):
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                self.aliases.sha(self.source)
                (self.inputs / 'extra').write_bytes(b'extra')

    def test_deleted_unhashed_file_rejected(self):
        extra = self.inputs / 'extra'
        extra.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                extra.unlink()

    def test_add_then_remove_still_changes_directory_stat(self):
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                extra = self.inputs / 'extra'
                extra.write_bytes(b'extra')
                extra.unlink()

    def test_empty_directory_addition_rejected(self):
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                (self.inputs / 'extra-directory').mkdir()

    def test_replacement_rejected(self):
        replacement = self.root / 'replacement'
        replacement.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                replacement.replace(self.source)

    def test_symlink_retarget_rejected(self):
        link = self.inputs / 'link'
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                self.aliases.sha(link)
                link.unlink()
                link.symlink_to(self.generated)

    def test_file_roots_supported_and_deleted_root_rejected(self):
        with self.scope(roots=[self.source]) as session:
            self.aliases.sha(self.source)
        self.assertEqual(session.stats()['unique_files'], 1)
        with self.assertRaises(OSError):
            with self.scope(roots=[self.source]):
                self.source.unlink()

    def test_symlink_directory_root_tracks_target_membership(self):
        alias = self.root / 'input-directory-alias'
        alias.symlink_to(self.inputs, target_is_directory=True)
        with self.scope(roots=[alias]) as session:
            self.aliases.sha(alias / self.source.name)
            self.aliases.sha(alias / self.source.name)
        self.assertEqual(session.stats()['cache_hits'], 1)
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope(roots=[alias]):
                (self.inputs / 'extra').write_bytes(b'extra')

    def test_output_mutation_before_first_immutable_read_is_still_excluded(self):
        with self.scope() as session:
            self.generated.write_bytes(b'rewritten before use')
            self.aliases.digest(self.generated)
            self.aliases.sha(self.source)
        self.assertEqual(session.stats()['unique_files'], 1)
        self.assertEqual(session.stats()['uncached_reads'], 1)

    def test_directory_deletion_and_unhashed_stat_mutation_rejected(self):
        directory = self.inputs / 'subdirectory'
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                directory.rmdir()
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                self.source.write_bytes(b'changed without hash call')

    def test_changes_during_final_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, 'during final rehash'):
            with self.scope() as session:
                self.aliases.sha(self.source)
                def mutate(path):
                    digest = h.RAW_SHA256(path)
                    path.write_bytes(b'tampered')
                    return digest
                session.hashes.hasher = mutate

    def test_addition_during_final_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope() as session:
                self.aliases.sha(self.source)
                def add(path):
                    digest = h.RAW_SHA256(path)
                    (self.inputs / 'extra').write_bytes(b'extra')
                    return digest
                session.hashes.hasher = add

    def test_exceptions_restore_aliases_and_do_not_mask_original_error(self):
        with self.assertRaisesRegex(RuntimeError, 'original oracle error'):
            with self.scope() as session:
                self.aliases.sha(self.source)
                session.hashes.reverify = Mock(side_effect=AssertionError('not on failed scope'))
                raise RuntimeError('original oracle error')
        self.assertIs(self.aliases.sha, h.RAW_SHA256)
        self.assertFalse(session.finished)
        with self.scope():
            self.aliases.sha(self.source)

    def test_stat_failure_at_finish_restores_aliases(self):
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            with self.scope():
                self.source.chmod(0o400)
        self.assertIs(self.aliases.sha, h.RAW_SHA256)

    def test_nested_and_cross_process_and_finished_session_rejected(self):
        with self.scope() as session:
            with self.assertRaisesRegex(RuntimeError, 'nested'):
                with self.scope():
                    pass
            with patch.object(h.os, 'getpid', return_value=session.pid + 1):
                with self.assertRaisesRegex(RuntimeError, 'another process'):
                    session.digest(self.source)
        with self.assertRaisesRegex(RuntimeError, 'already finished'):
            session.digest(self.source)

    def test_overlap_and_missing_root_rejected(self):
        for root in (self.output, self.generated, self.root):
            with self.subTest(root=root), self.assertRaisesRegex(ValueError, 'overlaps writable output'):
                with self.scope(roots=[root]):
                    pass
        with self.assertRaises(OSError):
            with self.scope(roots=[self.root / 'missing']):
                pass
        with self.assertRaisesRegex(ValueError, 'explicit immutable'):
            h.CoverageHashSession(self.output, [])

    def test_output_retarget_into_immutable_inputs_rejected(self):
        alias = self.root / 'output-alias'
        alias.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'overlaps writable output'):
            with h.scoped_hashes(alias, immutable_roots=[self.inputs], modules=[self.aliases]):
                alias.unlink()
                alias.symlink_to(self.inputs, target_is_directory=True)

    def test_no_process_tool_or_oracle_patch_and_real_child_still_works(self):
        invoke = recovery.full.batch.invoke
        oracle = recovery.sealed.evidence.Evidence.baseline_row
        popen, execv = subprocess.Popen, os.execv
        with self.scope():
            self.assertIs(recovery.full.batch.invoke, invoke)
            self.assertIs(recovery.sealed.evidence.Evidence.baseline_row, oracle)
            self.assertIs(subprocess.Popen, popen)
            self.assertIs(os.execv, execv)
            process = subprocess.run([sys.executable, '-B', '-c', 'print("tool allowed")'],
                                     capture_output=True, text=True, check=True)
            self.assertEqual(process.stdout.strip(), 'tool allowed')

    def test_default_patches_existing_helpers_without_changing_raw_exports(self):
        original = recovery.full.base.sha256
        with h.scoped_hashes(self.output, immutable_roots=[self.inputs]) as session:
            recovery.full.base.sha256(self.source)
            artifacts.sha256(self.source)
            h.bitmaps.digest(self.source)
            self.assertIs(recovery.RAW_SHA256, h.RAW_SHA256)
        self.assertEqual(session.stats()['cache_hits'], 2)
        self.assertIs(recovery.full.base.sha256, original)

    def test_critical_frozen_checks_still_compare_expected_digest(self):
        with self.scope(modules=[recovery.full.base]):
            digest = h.RAW_SHA256(self.source)
            recovery.full.base.check({str(self.source): digest})
            with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
                recovery.full.base.check({str(self.source): '0' * 64})

    def test_large_exact_file_allowlist_uses_constant_membership_work(self):
        other = self.root / 'undeclared'
        other.write_bytes(b'not immutable')
        with self.scope(roots=[self.source]) as session:
            session.file_targets = frozenset([self.source, *[
                self.inputs / f'receipt-{i}' for i in range(19768)]])
            self.assertEqual(len(session.file_targets), 19769)
            self.assertEqual(session.directory_targets, ())
            original = Path.is_relative_to
            with patch.object(Path, 'is_relative_to', autospec=True, side_effect=original) as relative:
                self.aliases.sha(self.source)
                self.aliases.digest(self.source)
                self.aliases.sha(other)
                self.aliases.sha(self.generated)
            self.assertLessEqual(relative.call_count, 24)
        self.assertEqual(session.stats()['cache_hits'], 1)
        self.assertEqual(session.stats()['unique_files'], 1)
        self.assertEqual(session.stats()['final_rehashed'], 1)
        self.assertEqual(session.stats()['uncached_reads'], 2)

    def test_file_and_directory_indexes_do_not_rescan_targets(self):
        exact = [self.inputs / f'receipt-{i}' for i in range(256)]
        for path in exact:
            path.write_bytes(b'receipt')
        directory = self.root / 'immutable-directory'
        directory.mkdir()
        nested = directory / 'nested'
        nested.write_bytes(b'directory input')
        class NoScan(dict):
            def items(self):
                raise AssertionError('unexpected all-root scan')
            def values(self):
                raise AssertionError('unexpected all-root scan')
            def __iter__(self):
                raise AssertionError('unexpected all-root scan')
        with self.scope(roots=[*exact, directory]) as session:
            self.assertEqual(session.file_targets, frozenset(exact))
            self.assertEqual(session.directory_targets, (directory,))
            session.targets = NoScan(session.targets)
            session._input_ancestors = NoScan(session._input_ancestors)
            session._directory_sources = NoScan(session._directory_sources)
            session.check_output_boundary()
            self.aliases.sha(exact[0])
            self.aliases.sha(nested)
            self.aliases.sha(self.generated)
        self.assertEqual(session.stats()['unique_files'], 2)
        self.assertEqual(session.stats()['final_rehashed'], 2)

    def test_exact_file_roots_allow_new_sibling_scripts(self):
        with self.scope(roots=[self.source]) as session:
            self.aliases.sha(self.source)
            (self.inputs / 'new-agent-script.py').write_bytes(b'new sibling')
        self.assertTrue(session.finished)
        self.assertEqual(session.stats()['final_rehashed'], 1)

    def test_exact_file_root_replacement_and_stat_change_rejected(self):
        for change in ('replace', 'chmod'):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'membership/stat changed'):
                with self.scope(roots=[self.source]):
                    if change == 'replace':
                        replacement = self.root / 'replacement'
                        replacement.write_bytes(b'original')
                        replacement.replace(self.source)
                    else:
                        self.source.chmod(0o400)

    def test_exact_file_boundary_index_rejects_output_retarget_to_parent(self):
        alias = self.root / 'output-alias'
        alias.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'overlaps writable output'):
            with h.scoped_hashes(alias, immutable_roots=[self.source], modules=[self.aliases]):
                alias.unlink()
                alias.symlink_to(self.inputs, target_is_directory=True)


if __name__ == '__main__':
    unittest.main()
