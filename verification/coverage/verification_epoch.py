"""Single-process immutable evidence capture, not a live-filesystem attestation.

Each canonical endpoint is read and hashed once per epoch. Cached bytes describe
that capture only: callers need a fresh epoch at each integrity boundary unless
the consumed filesystem is independently proven immutable. Metadata guards can
reject changes but never replace a content hash or prove continued immutability.
No receipt, EDA integration, global cache, or persistent cache is provided.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType


class EpochError(ValueError):
    pass


@dataclass(frozen=True)
class AliasBinding:
    link_target: str
    resolved: str
    sha256: str


@dataclass(frozen=True)
class CapturedBytes:
    endpoint: str
    sha256: str
    data: bytes


def _path(value):
    text = os.fspath(value)
    if not isinstance(text, str) or not os.path.isabs(text):
        raise EpochError('Absolute path required')
    if text != os.path.normpath(text):
        raise EpochError('Noncanonical lexical path')
    return Path(text)


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise EpochError('Exact lowercase SHA256 required')
    return value


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _freeze(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise EpochError('Nonfinite JSON number')
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise EpochError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise EpochError('Nonfinite JSON constant: ' + value)


class VerificationEpoch:
    """Capture exact pins into memory; failure poisons the entire epoch.

    Alias permissions must come from independently sealed evidence, not local
    discovery. All provided pins remain obligations: finish() rejects omissions.
    Guard metadata is checked on reuse, but the return value is always the
    immutable captured version, never a claim about subsequently writable files.
    """

    def __init__(self, pins, aliases=None):
        self._expected = {}
        self._aliases = {}
        self._captures = {}
        self._guards = {}
        self._json = {}
        self._visited = set()
        self._failed = False
        self._closed = False
        self._reads = self._hashes = self._parses = 0
        for name, expected in pins.items():
            self._register(_path(name), _sha(expected))
        for name, binding in (aliases or {}).items():
            name = str(_path(name))
            if not isinstance(binding, AliasBinding):
                raise EpochError('Explicit AliasBinding required')
            endpoint = _path(binding.resolved)
            expected = _sha(binding.sha256)
            if not isinstance(binding.link_target, str) or not binding.link_target:
                raise EpochError('Exact literal link target required')
            if name not in self._expected or self._expected[name] != expected:
                raise EpochError('Alias missing exact pin')
            if str(endpoint) not in self._expected or self._expected[str(endpoint)] != expected:
                raise EpochError('Alias endpoint missing/conflicting pin')
            if name == str(endpoint):
                raise EpochError('Alias cannot name itself')
            self._aliases[name] = binding

    def _register(self, path, expected):
        name = str(path)
        if name in self._expected and self._expected[name] != expected:
            raise EpochError('Conflicting expected SHA: ' + name)
        self._expected[name] = expected

    def _active(self):
        if self._closed or self._failed:
            raise EpochError('Epoch is closed or failed')

    def _guard(self, path):
        info = path.lstat()
        key = str(path)
        identity = _identity(info)
        if key in self._guards and self._guards[key] != identity:
            raise EpochError('Filesystem identity changed: ' + key)
        return info, identity

    def _resolve(self, path):
        name = str(path)
        info, identity = self._guard(path)
        if stat.S_ISLNK(info.st_mode):
            binding = self._aliases.get(name)
            if binding is None:
                raise EpochError('Unapproved symbolic link: ' + name)
            if path.parent.resolve(strict=True) != path.parent:
                raise EpochError('Aliased parent path')
            if os.readlink(path) != binding.link_target:
                raise EpochError('Literal symbolic link changed')
            endpoint = _path(binding.resolved)
            if path.resolve(strict=True) != endpoint:
                raise EpochError('Resolved symbolic link changed')
        else:
            if name in self._aliases:
                raise EpochError('Approved symbolic link replaced')
            endpoint = path
        if endpoint.resolve(strict=True) != endpoint:
            raise EpochError('Noncanonical endpoint')
        endpoint_info, endpoint_identity = self._guard(endpoint)
        if not stat.S_ISREG(endpoint_info.st_mode):
            raise EpochError('Regular file endpoint required')
        return endpoint, identity, endpoint_identity

    def read(self, path, expected_sha256):
        self._active()
        try:
            path = _path(path)
            expected = _sha(expected_sha256)
            name = str(path)
            if name not in self._expected or self._expected[name] != expected:
                raise EpochError('Unknown/conflicting requested pin: ' + name)
            endpoint, path_identity, endpoint_identity = self._resolve(path)
            key = str(endpoint)
            if key not in self._captures:
                # O_NOFOLLOW plus fstat binds bytes to the inspected endpoint.
                fd = os.open(endpoint, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as stream:
                    if _identity(os.fstat(stream.fileno())) != endpoint_identity:
                        raise EpochError('Endpoint changed before read')
                    data = stream.read()
                    if _identity(os.fstat(stream.fileno())) != endpoint_identity:
                        raise EpochError('Endpoint changed during read')
                self._reads += 1
                actual = hashlib.sha256(data).hexdigest()
                self._hashes += 1
                if actual != expected or len(data) != endpoint_identity[3]:
                    raise EpochError('Captured bytes differ from expected SHA')
                self._captures[key] = CapturedBytes(key, actual, data)
            capture = self._captures[key]
            if capture.sha256 != expected:
                raise EpochError('Cached endpoint conflicts with expected SHA')
            # Recheck the path/endpoint after capture, including literal links.
            after, after_path, after_endpoint = self._resolve(path)
            if (after, after_path, after_endpoint) != (endpoint, path_identity, endpoint_identity):
                raise EpochError('Path changed during capture')
            self._guards[name] = path_identity
            self._guards[key] = endpoint_identity
            self._visited.add(name)
            return capture
        except Exception:
            self._failed = True
            raise

    def json(self, path, expected_sha256):
        capture = self.read(path, expected_sha256)
        try:
            if capture.endpoint not in self._json:
                value = json.loads(capture.data, object_pairs_hook=_pairs,
                                   parse_constant=_constant)
                self._json[capture.endpoint] = _freeze(value)
                self._parses += 1
            return self._json[capture.endpoint]
        except Exception:
            self._failed = True
            raise

    def finish(self):
        """Check every pin/path guard; does not assert fresh current content."""
        self._active()
        try:
            if self._visited != set(self._expected):
                raise EpochError('Unverified pins remain')
            for name in self._expected:
                self._resolve(Path(name))
            return self.statistics
        except Exception:
            self._failed = True
            raise

    @property
    def statistics(self):
        return MappingProxyType(dict(reads=self._reads, hashes=self._hashes,
                                     parses=self._parses, verified_paths=len(self._visited)))

    def close(self):
        self._closed = True
        self._captures.clear()
        self._json.clear()
