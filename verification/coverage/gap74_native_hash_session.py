"""Read deduplication only: exact allowlist, topology/tree seals, uncached finish."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path
import stat
import threading
import time

ROOT = Path(__file__).resolve().parents[2]


def absolute(path):
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("ambiguous dot-dot hash path")
    return Path(os.path.abspath(path if path.is_absolute() else ROOT / path))


def stat_key(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)


def file_identity(path):
    target, link = os.stat(path), os.lstat(path)
    if not stat.S_ISREG(target.st_mode):
        raise ValueError("not a regular hash input: %s" % path)
    return stat_key(target), stat_key(link)


def topology_key(path):
    value = os.lstat(path)
    if stat.S_ISLNK(value.st_mode):
        return ("link", stat_key(value), os.readlink(path))
    if not stat.S_ISDIR(value.st_mode):
        raise ValueError("non-directory input ancestor: %s" % path)
    # Sibling campaigns may change ancestor directory timestamps, not topology.
    return ("directory", value.st_dev, value.st_ino, value.st_mode)


def tree_snapshot(root):
    result = {}
    def visit(path, value):
        result[str(path)] = (stat_key(value), os.readlink(path)
                             if stat.S_ISLNK(value.st_mode) else None)
        if stat.S_ISDIR(value.st_mode):
            with os.scandir(path) as listing:
                for entry in listing:
                    visit(Path(entry.path), entry.stat(follow_symlinks=False))
    visit(root, os.lstat(root))
    return result


class NativeHashSession:
    """No persistent cache and no oracle/report-result caching.

    Each hit still compares target and leaf lstat identities. Resolved parent
    paths are indexed once; every ancestor topology binding is checked at the
    publication boundary. Undeclared inputs are never cache hits, but their
    initial bytes are still bound and rehashed at finish. Writable outputs are
    always uncached and never treated as immutable inputs.
    """
    def __init__(self, outputs, *, immutable_files, immutable_trees=(), workers=4):
        if type(workers) is not int or not 1 <= workers <= 8:
            raise ValueError("hash worker count must be 1..8")
        self.outputs = tuple(absolute(p) for p in outputs)
        if not self.outputs:
            raise ValueError("explicit writable outputs required")
        self.output_targets = tuple(p.resolve() for p in self.outputs)
        self.output_prefixes = tuple((str(p), str(p).rstrip(os.sep) + os.sep)
            for p in dict.fromkeys((*self.outputs, *self.output_targets)))
        self.paths = {os.fspath(p): absolute(p) for p in immutable_files}
        self.cacheable = frozenset(str(p) for p in self.paths.values())
        if not self.cacheable:
            raise ValueError("explicit immutable file allowlist required")
        self.workers, self.pid = workers, os.getpid()
        self.entries, self.parents, self.topology, self.trees = {}, {}, {}, {}
        self.hits = self.bytes = self.reverified = self.raw_reads = 0
        self.identity_calls = self.content_reads = 0
        self.finished = False
        self.started = time.monotonic()
        self.stop = threading.Event()
        for name in self.cacheable:
            self._check_overlap(absolute(name))
        for name in immutable_trees:
            path = absolute(name)
            target = path.resolve(strict=True)
            self._check_overlap(path)
            self._check_overlap(target)
            for root in (path, target):
                if root not in self.trees:
                    self._bind_parent(root.parent)
                    self.trees[root] = tree_snapshot(root)

    def _live(self):
        if os.getpid() != self.pid:
            raise RuntimeError("native hash session is process-local")
        if self.finished:
            raise RuntimeError("native hash session already finished")
        if self.stop.is_set():
            raise RuntimeError("native hash session aborted")

    def _writable(self, path):
        key = str(path)
        return any(key == root or key.startswith(prefix) for root, prefix in self.output_prefixes)

    def _path(self, path):
        key = os.fspath(path)
        result = self.paths.get(key)
        if result is None:
            result = absolute(path)
            self.paths[key] = result
        return result

    def _check_overlap(self, path):
        if self._writable(path) or any(root.is_relative_to(path) for root in self.outputs):
            raise ValueError("immutable input overlaps output: %s" % path)

    def _bind_parent(self, parent):
        if parent not in self.parents:
            target = parent.resolve(strict=True)
            for path in dict.fromkeys((parent, *parent.parents, target, *target.parents)):
                actual = topology_key(path)
                if path in self.topology and self.topology[path] != actual:
                    raise ValueError("input ancestor topology changed: %s" % path)
                self.topology[path] = actual
            self.parents[parent] = target
        return self.parents[parent]

    def _identity(self, path):
        self.identity_calls += 1
        return file_identity(path)

    def _enroll(self, path):
        target_parent = self._bind_parent(path.parent)
        identity = self._identity(path)
        target = (path.resolve(strict=True) if stat.S_ISLNK(identity[1][2])
                  else target_parent / path.name)
        self._check_overlap(target)
        self._bind_parent(target.parent)
        return identity

    def _read(self, path, expected):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            if stat_key(os.fstat(stream.fileno())) != expected[0]:
                raise ValueError("input changed before content read: %s" % path)
            while True:
                if self.stop.is_set():
                    raise RuntimeError("native hash batch cancelled")
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            if stat_key(os.fstat(stream.fileno())) != expected[0]:
                raise ValueError("input changed during content read: %s" % path)
        if file_identity(path) != expected:
            raise ValueError("input changed after content read: %s" % path)
        return digest.hexdigest()

    def digest(self, path):
        self._live()
        path = self._path(path)
        key = str(path)
        if self._writable(path):
            self.raw_reads += 1
            digest = self._read(path, self._identity(path))
            self.content_reads += 1
            return digest
        if key in self.entries:
            bound, previous = self.entries[key]
            if self._identity(path) != bound:
                raise ValueError("input identity changed: %s" % path)
            if key in self.cacheable:
                self.hits += 1
                return previous
        else:
            bound, previous = self._enroll(path), None
        digest = self._read(path, bound)
        self.content_reads += 1
        if previous is not None and digest != previous:
            raise ValueError("uncached input changed: %s" % path)
        if previous is None:
            self.bytes += bound[0][3]
        self.entries[key] = (bound, digest)
        if key not in self.cacheable:
            self.raw_reads += 1
        return digest

    def _batch(self, jobs, accept):
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            pending = {pool.submit(self._read, path, bound): (path, bound, expected)
                       for path, bound, expected in jobs}
            for future in as_completed(pending):
                path, bound, expected = pending[future]
                digest = future.result()
                if digest != expected:
                    raise ValueError("uncached content SHA differs: %s" % path)
                accept(path, bound, digest)
        except BaseException:
            self.stop.set()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def prehash(self, expected):
        self._live()
        jobs = []
        names = set()
        for name, digest in expected.items():
            path = self._path(name)
            if str(path) in names:
                raise ValueError("duplicate normalized prehash input")
            names.add(str(path))
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid expected SHA256")
            if str(path) not in self.cacheable or self._writable(path):
                raise ValueError("prehash input is not explicitly immutable: %s" % path)
            if str(path) in self.entries:
                if self.digest(path) != digest:
                    raise ValueError("prehash expected SHA differs")
            else:
                jobs.append((path, self._enroll(path), digest))
        def accept(path, bound, digest):
            self.entries[str(path)] = (bound, digest)
            self.bytes += bound[0][3]
            self.content_reads += 1
        self._batch(jobs, accept)

    def check_membership_and_topology(self):
        self._live()
        if tuple(p.resolve() for p in self.outputs) != self.output_targets:
            raise ValueError("writable output target changed")
        for path, expected in self.topology.items():
            if topology_key(path) != expected:
                raise ValueError("input ancestor topology changed: %s" % path)
        for root, expected in self.trees.items():
            if tree_snapshot(root) != expected:
                raise ValueError("immutable tree membership/stat changed: %s" % root)

    def reverify(self):
        self._live()
        self.check_membership_and_topology()
        jobs = []
        for name, (bound, digest) in self.entries.items():
            path = Path(name)
            if self._identity(path) != bound:
                raise ValueError("input identity changed before final rehash: %s" % path)
            jobs.append((path, bound, digest))
        def accept(path, bound, digest):
            self.reverified += 1
        # Never call digest() here: every bound content is read again uncached.
        self._batch(jobs, accept)
        self.check_membership_and_topology()
        for name, (bound, _) in self.entries.items():
            if self._identity(Path(name)) != bound:
                raise ValueError("input identity changed after final rehash: %s" % name)
        if self.reverified != len(self.entries):
            raise ValueError("incomplete uncached final rehash")
        self.finished = True

    def stats(self):
        return dict(unique_files=len(self.entries), cache_hits=self.hits,
                    initial_bytes=self.bytes, final_rehashed=self.reverified,
                    content_reads=self.content_reads, uncached_reads=self.raw_reads,
                    identity_checks_main_thread=self.identity_calls, resolved_parents=len(self.parents),
                    topology_nodes=len(self.topology), immutable_trees=len(self.trees),
                    workers=self.workers, finished=self.finished,
                    elapsed_s=round(time.monotonic() - self.started, 6))
