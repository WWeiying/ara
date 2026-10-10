"""Process-local SHA read deduplication, not an admission or oracle layer.

Import all collector adapters before entering scoped_hashes. Declare immutable
files/directories explicitly, disjoint from the writable output directory. Only
existing verification-module hash aliases are patched. Normal scope exit checks
tree membership/stat and rehashes every cached input without using the cache.
Failed scopes propagate their error without performing a publication check.
Do not publish a final PASS marker until the scope has exited successfully.
"""
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import sys
from unittest.mock import patch

from recover_gap65_report_only import HashSession, RAW_SHA256
import coverage_bitmap_delta as bitmaps

RAW_BITMAP_DIGEST = bitmaps.digest
HERE = Path(__file__).resolve()
VERIFICATION = HERE.parents[1]
ROOT = VERIFICATION.parent
_active = None


def absolute(path):
    path = Path(path)
    return Path(os.path.abspath(path if path.is_absolute() else ROOT / path))


def node_identity(path):
    stat = path.lstat()
    return (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns, stat.st_nlink)


def tree_snapshot(path):
    """Do not follow directory symlinks; cached target bytes have separate pins."""
    result = {}

    def visit(node):
        result[str(node)] = node_identity(node)
        if node.is_dir() and not node.is_symlink():
            with os.scandir(node) as entries:
                children = sorted(Path(entry.path) for entry in entries)
            for child in children:
                visit(child)

    visit(path)
    return result


class CoverageHashSession:
    def __init__(self, output, immutable_roots):
        self.output = absolute(output)
        self.output_target = self.output.resolve()
        self.roots = tuple(dict.fromkeys(absolute(p) for p in immutable_roots))
        if not self.roots:
            raise ValueError('explicit immutable input roots required')
        self.pid = os.getpid()
        self.finished = False
        self.hashes = HashSession(hasher=RAW_SHA256)
        self.raw_reads = 0
        self.targets = {}
        self.snapshots = {}
        file_targets, directory_targets = set(), set()
        self._input_ancestors = {}
        self._directory_sources = {}
        for root in self.roots:
            target = root.resolve(strict=True)
            is_dir = root.is_dir()
            self.targets[root] = (target, is_dir)
            (directory_targets if is_dir else file_targets).add(target)
            # Index descendants once: boundary checks must not scan every file.
            for source in (root, target):
                for ancestor in (source, *source.parents):
                    self._input_ancestors.setdefault(ancestor, root)
                if is_dir:
                    self._directory_sources[source] = root
        self.file_targets = frozenset(file_targets)
        self.directory_targets = tuple(sorted(directory_targets))
        self.check_output_boundary()
        for root in self.roots:
            self.snapshots[root] = tree_snapshot(root)
            target, _ = self.targets[root]
            if target not in self.snapshots:
                self.snapshots[target] = tree_snapshot(target)

    def check_process(self):
        if os.getpid() != self.pid:
            raise RuntimeError('hash session cannot be reused in another process')
        if self.finished:
            raise RuntimeError('hash session already finished')

    def check_output_boundary(self):
        outputs = (self.output, self.output_target, self.output.resolve())
        for output in dict.fromkeys(outputs):
            root = self._input_ancestors.get(output)
            if root is None:
                root = next((self._directory_sources[p] for p in (output, *output.parents)
                             if p in self._directory_sources), None)
            if root is not None:
                raise ValueError(f'immutable input overlaps writable output: {root}')

    def digest(self, path):
        self.check_process()
        path = absolute(path)
        target = path.resolve(strict=True)
        outputs = (self.output, self.output_target, self.output.resolve())
        writable = any(path.is_relative_to(p) or target.is_relative_to(p) for p in outputs)
        if writable:
            self.raw_reads += 1
            return RAW_SHA256(path)
        immutable = target in self.file_targets or any(target.is_relative_to(root)
                                                      for root in self.directory_targets)
        if not immutable:
            self.raw_reads += 1
            return RAW_SHA256(path)
        return self.hashes.digest(path)

    def check_trees(self):
        self.check_output_boundary()
        for root, expected in self.snapshots.items():
            if tree_snapshot(root) != expected:
                raise ValueError(f'immutable input tree membership/stat changed: {root}')

    def finish(self):
        self.check_process()
        self.check_trees()
        self.hashes.reverify()
        self.check_trees()
        self.hashes.assert_unchanged()
        self.finished = True

    def stats(self):
        return dict(self.hashes.stats(), uncached_reads=self.raw_reads,
                    immutable_roots=len(self.roots), finished=self.finished)


def verification_modules():
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).resolve().is_relative_to(VERIFICATION):
            yield module


@contextmanager
def scoped_hashes(output, *, immutable_roots, modules=None):
    """Share one cache across prepare/summarize calls; leave tool calls untouched.

modules optionally limits alias patching to an explicit iterable of already
imported module objects. Otherwise use loaded modules under verification/. RAW_*
exports and this module are never patched. Nested sessions are rejected.
"""
    global _active
    if _active is not None:
        raise RuntimeError('nested coverage hash sessions are not supported')
    session = CoverageHashSession(output, immutable_roots)
    callback = session.digest
    _active = session
    try:
        with ExitStack() as stack:
            selected = tuple(verification_modules() if modules is None else modules)
            for module in dict.fromkeys(selected):
                if getattr(module, '__file__', None) and Path(module.__file__).resolve() == HERE:
                    continue
                for name, value in list(vars(module).items()):
                    if not name.startswith('RAW_') and (value is RAW_SHA256 or value is RAW_BITMAP_DIGEST):
                        stack.enter_context(patch.object(module, name, callback))
            yield session
            session.finish()
    finally:
        _active = None
