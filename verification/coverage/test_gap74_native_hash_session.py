"""Hash-only negatives, including a genuinely cold final-content failure."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import gap74_native_hash_session as h


class HashSessionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="gap74-hash-")))
        self.inputs, self.output = self.root / "inputs", self.root / "output"
        self.inputs.mkdir()
        self.output.mkdir()
        self.path = self.inputs / "data"
        self.path.write_bytes(b"original")

    def session(self, trees=True, files=None, workers=2):
        return h.NativeHashSession([self.output], immutable_files=files or [self.path],
            immutable_trees=[self.inputs] if trees else [], workers=workers)

    def test_one_initial_read_shared_hits_then_all_uncached_reads(self):
        session = self.session()
        with patch.object(session, "_read", wraps=session._read) as reader:
            expected = session.digest(self.path)
            self.assertEqual(session.digest(str(self.path)), expected)
            self.assertEqual(session.digest(self.path), expected)
            self.assertEqual(reader.call_count, 1)
            session.reverify()
            self.assertEqual(reader.call_count, 2)
        self.assertEqual(session.reverified, len(session.entries))
        self.assertTrue(session.finished)

    def test_bulk_prehash_validates_every_expected_sha(self):
        paths = [self.inputs / ("file-%d" % i) for i in range(64)]
        for i, path in enumerate(paths):
            path.write_bytes(bytes([i]) * 1024)
        files = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        session = self.session(files=paths, workers=4)
        session.prehash(files)
        for path, digest in files.items():
            self.assertEqual(session.digest(path), digest)
        session.reverify()
        self.assertEqual(session.reverified, 64)
        self.assertEqual(session.stats()["initial_bytes"], 65536)

    def test_small_offline_stage_cost_sample_not_full_prepare(self):
        from coverage_hash_session import CoverageHashSession
        paths = [self.inputs / ("cost-%d" % i) for i in range(64)]
        for path in paths:
            path.write_bytes(b"x" * 65536)
        expected = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        samples = {}
        for name in ("frozen_hash_helper_only", "gap74_exact_files"):
            started = time.perf_counter()
            session = (CoverageHashSession(self.output, paths) if name.startswith("frozen") else
                       h.NativeHashSession([self.output], immutable_files=paths, immutable_trees=[self.inputs]))
            construction = time.perf_counter() - started
            started = time.perf_counter()
            if name.startswith("frozen"):
                for path in paths:
                    self.assertEqual(session.digest(path), expected[str(path)])
            else:
                session.prehash(expected)
            initial = time.perf_counter() - started
            started = time.perf_counter()
            for i in range(4096):
                session.digest(paths[i % 64])
            hits = time.perf_counter() - started
            started = time.perf_counter()
            if name.startswith("frozen"):
                session.finish()
            else:
                session.reverify()
            tail = time.perf_counter() - started
            self.assertEqual(session.stats()["final_rehashed"], 64)
            samples[name] = dict(construction_s=construction, initial_s=initial,
                                 hits4096_s=hits, cold_final64_s=tail)
        print("GAP74_SMALL_HASH_COST " + json.dumps(dict(files=64, bytes=4194304,
            samples=samples, full_prepare=False, native_qualified=False), sort_keys=True))

    def test_wrong_expected_digest_and_invalid_digest_rejected(self):
        for digest in ("0" * 64, "x" * 64, "short", None):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.session().prehash({str(self.path): digest})

    def test_aborted_batch_cannot_be_reused(self):
        session = self.session()
        with self.assertRaises(ValueError):
            session.prehash({str(self.path): "0" * 64})
        self.assertFalse(session.finished)
        with self.assertRaisesRegex(RuntimeError, "aborted"):
            session.digest(self.path)

    def test_mutation_with_restored_mtime_rejected_on_hit(self):
        session = self.session()
        session.digest(self.path)
        before = self.path.stat()
        self.path.write_bytes(b"tampered")
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "identity changed"):
            session.digest(self.path)

    def test_cold_final_sha_rejects_even_when_all_metadata_is_spoofed(self):
        session = self.session(trees=False)
        session.digest(self.path)
        original_stat = self.path.stat()
        bound = session.entries[str(self.path)][0]
        self.path.write_bytes(b"tampered")
        # Only the content read remains discriminating: both stat routes lie.
        with patch.object(h, "file_identity", return_value=bound), \
             patch.object(h.os, "fstat", return_value=original_stat), \
             self.assertRaisesRegex(ValueError, "uncached content SHA differs"):
            session.reverify()
        self.assertFalse(session.finished)
        self.assertEqual(session.reverified, 0)

    def test_mutation_during_read_rejected(self):
        session = self.session()
        bound = session._enroll(self.path)
        real_identity = h.file_identity
        def mutate(path):
            path.write_bytes(b"tampered")
            return real_identity(path)
        with patch.object(h, "file_identity", side_effect=mutate), self.assertRaises(ValueError):
            session._read(self.path, bound)

    def test_added_deleted_empty_directory_and_unhashed_stat_rejected(self):
        extra = self.inputs / "unhashed"
        extra.write_bytes(b"extra")
        for mutation in (lambda: (self.inputs / "added").write_bytes(b"new"),
                         extra.unlink, lambda: (self.inputs / "newdir").mkdir(),
                         lambda: self.path.chmod(0o400)):
            with self.subTest(mutation=mutation):
                session = self.session()
                session.digest(self.path)
                mutation()
                with self.assertRaisesRegex(ValueError, "membership/stat"):
                    session.reverify()

    def test_add_then_remove_changes_declared_directory_identity(self):
        session = self.session()
        session.digest(self.path)
        extra = self.inputs / "added"
        extra.write_bytes(b"new")
        extra.unlink()
        with self.assertRaises(ValueError):
            session.reverify()

    def test_member_added_during_uncached_batch_rejected(self):
        session = self.session()
        session.digest(self.path)
        read = session._read
        def add(path, expected):
            result = read(path, expected)
            (self.inputs / "added").write_bytes(b"new")
            return result
        with patch.object(session, "_read", side_effect=add), self.assertRaisesRegex(ValueError, "membership"):
            session.reverify()
        self.assertFalse(session.finished)

    def test_same_bytes_file_replacement_rejected(self):
        session = self.session()
        session.digest(self.path)
        replacement = self.root / "replacement"
        replacement.write_bytes(b"original")
        replacement.replace(self.path)
        with self.assertRaises(ValueError):
            session.digest(self.path)

    def test_leaf_symlink_retarget_rejected(self):
        link = self.inputs / "link"
        other = self.inputs / "other"
        other.write_bytes(b"original")
        link.symlink_to(self.path)
        session = self.session(files=[link])
        session.digest(link)
        link.unlink()
        link.symlink_to(other)
        with self.assertRaises(ValueError):
            session.digest(link)

    def test_same_target_parent_symlink_replacement_rejected_at_boundary(self):
        link = self.root / "alias"
        link.symlink_to(self.inputs, target_is_directory=True)
        source = link / "data"
        session = self.session(trees=False, files=[source])
        session.digest(source)
        link.unlink()
        link.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "topology"):
            session.reverify()

    def test_output_always_raw_and_unbound(self):
        session = self.session()
        path = self.output / "generated"
        path.write_bytes(b"one")
        first = session.digest(path)
        path.write_bytes(b"two")
        self.assertNotEqual(session.digest(path), first)
        self.assertEqual(session.entries, {})
        self.assertEqual(session.raw_reads, 2)

    def test_output_prefix_sibling_not_mistaken_for_output(self):
        sibling = Path(str(self.output) + "-input")
        sibling.write_bytes(b"immutable")
        session = self.session(trees=False, files=[sibling])
        session.digest(sibling)
        session.digest(sibling)
        self.assertEqual(session.hits, 1)

    def test_output_alias_and_immutable_overlap_rejected(self):
        path = self.output / "data"
        path.write_bytes(b"output")
        alias = self.inputs / "output-alias"
        alias.symlink_to(path)
        for source in (path, alias):
            with self.subTest(source=source), self.assertRaises(ValueError):
                session = self.session(trees=False, files=[source])
                session.digest(source)

    def test_output_root_overlap_and_output_retarget_rejected(self):
        with self.assertRaises(ValueError):
            h.NativeHashSession([Path("/")], immutable_files=[self.path])
        alias = self.root / "output-link"
        alias.symlink_to(self.output, target_is_directory=True)
        session = h.NativeHashSession([alias], immutable_files=[self.path])
        session.digest(self.path)
        alias.unlink()
        alias.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "output target changed"):
            session.reverify()

    def test_undeclared_input_never_cached_but_finally_rehashed(self):
        session = self.session(trees=False)
        other = self.root / "other"
        other.write_bytes(b"uncached input")
        with patch.object(session, "_read", wraps=session._read) as read:
            session.digest(other)
            session.digest(other)
            session.reverify()
            self.assertEqual(read.call_count, 3)
        self.assertEqual(session.hits, 0)
        self.assertEqual(session.reverified, 1)

    def test_hits_do_not_resolve_paths_or_scan_allowlist(self):
        session = self.session(trees=False)
        session.digest(self.path)
        session.cacheable = frozenset([str(self.path), *["/unused/%d" % i for i in range(19768)]])
        with patch.object(Path, "resolve", side_effect=AssertionError("resolve on hit")), \
             patch.object(h, "absolute", side_effect=AssertionError("normalize on hit")):
            for _ in range(32):
                session.digest(self.path)
        self.assertEqual(session.hits, 32)

    def test_finished_cross_process_dotdot_and_invalid_workers_rejected(self):
        session = self.session()
        with patch.object(h.os, "getpid", return_value=session.pid + 1), self.assertRaises(RuntimeError):
            session.digest(self.path)
        with self.assertRaises(ValueError):
            session.digest(self.inputs / ".." / "inputs" / "data")
        for workers in (0, 9, True):
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                self.session(workers=workers)
        session.digest(self.path)
        session.reverify()
        with self.assertRaises(RuntimeError):
            session.reverify()


if __name__ == "__main__":
    unittest.main()
