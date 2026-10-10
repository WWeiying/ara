"""Unwired successor reader for one explicit historical-report population.

Only independently pinned, predeclared JSON is parsed. Hash-only inputs stream
once; JSON hashes and parses the same bytes once, then releases the raw buffer.
Results are immutable captured evidence, NOT fresh live-file attestations. A
future launcher must consume a proven immutable snapshot and use a separate
reader after execution. This module neither launches EDA nor qualifies policies.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from types import MappingProxyType

import verification_epoch as core

CHUNK_BYTES = 1024 * 1024


def require(value, message):
    if not value:
        raise core.EpochError(message)


def immutable(value):
    # Child objects have already been frozen by the JSON object-pairs hook.
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, list):
        return tuple(immutable(item) for item in value)
    if isinstance(value, float):
        require(math.isfinite(value), 'Nonfinite JSON number')
    return value


def object_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = immutable(value)
    return MappingProxyType(result)


@dataclass(frozen=True)
class HashCapture:
    endpoint: str
    sha256: str
    size: int


@dataclass(frozen=True, init=False, eq=False)
class ConfigView(Mapping):
    """Read-only shallow field facade; nested evidence is shared, never copied."""

    def __init__(self, config, overrides):
        require(isinstance(config, MappingProxyType), 'Frozen JSON object required')
        object.__setattr__(self, '_config', config)
        # Replacement fields must themselves be immutable JSON/scalars.
        for value in overrides.values():
            require(isinstance(value, (str, int, float, bool, type(None))),
                    'Mutable field replacement forbidden')
            immutable(value)
        object.__setattr__(self, '_overrides', MappingProxyType(dict(overrides)))

    def __getitem__(self, key):
        return self._overrides[key] if key in self._overrides else self._config[key]

    def __iter__(self):
        return iter(dict.fromkeys((*self._config, *self._overrides)))

    def __len__(self):
        return len(set(self._config) | set(self._overrides))

    def __deepcopy__(self, memo):
        return self


class PopulationReaderEpoch:
    """Exact-pin capture interface for a future reader context, not a launcher.

    Pins/aliases come from reviewed sealed authority. finish() rejects any
    unvisited path, including endpoint pins reached only through an alias.
    Metadata guards can reject visible changes but cannot prove immutability.
    No cache is shared between instances or integrity boundaries.
    """

    def __init__(self, pins, aliases=None, *, json_paths=(),
                 max_json_bytes=128 * 1024 * 1024,
                 max_total_json_bytes=256 * 1024 * 1024):
        require(type(max_json_bytes) is int and max_json_bytes > 0 and
                type(max_total_json_bytes) is int and max_total_json_bytes > 0,
                'Explicit positive integer JSON budgets required')
        self._resolver = core.VerificationEpoch(pins, aliases)
        self.pins = MappingProxyType(dict(self._resolver._expected))
        self._json_endpoints = set()
        for path in json_paths:
            name = str(core._path(path))
            require(name in self.pins, 'Unpinned JSON declaration')
            alias = self._resolver._aliases.get(name)
            self._json_endpoints.add(alias.resolved if alias else name)
        self._captures, self._json, self._visited = {}, {}, set()
        self._failed = self._closed = False
        self._limit, self._total_limit = max_json_bytes, max_total_json_bytes
        self._json_bytes = self._reads = self._hashed_bytes = self._parses = 0

    def _active(self):
        require(not self._failed and not self._closed, 'Reader epoch closed or failed')

    def _capture(self, path, expected):
        self._active()
        try:
            path = core._path(path)
            expected = core._sha(expected)
            name = str(path)
            require(self.pins.get(name) == expected, 'Unknown/conflicting exact pin: ' + name)
            endpoint, path_id, endpoint_id = self._resolver._resolve(path)
            key = str(endpoint)
            if key not in self._captures:
                is_json = key in self._json_endpoints
                if is_json:
                    require(endpoint_id[3] <= self._limit and
                            self._json_bytes + endpoint_id[3] <= self._total_limit,
                            'Declared JSON capture budget exceeded')
                digest = hashlib.sha256()
                data = bytearray() if is_json else None
                count = 0
                fd = os.open(endpoint, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as stream:
                    require(core._identity(os.fstat(stream.fileno())) == endpoint_id,
                            'Endpoint changed before capture')
                    while True:
                        block = stream.read(CHUNK_BYTES)
                        if not block:
                            break
                        count += len(block)
                        require(count <= endpoint_id[3], 'Endpoint grew during capture')
                        digest.update(block)
                        if is_json:
                            data.extend(block)
                    require(core._identity(os.fstat(stream.fileno())) == endpoint_id,
                            'Endpoint changed during capture')
                actual = digest.hexdigest()
                require(count == endpoint_id[3] and actual == expected, 'Exact captured SHA differs')
                self._reads += 1
                self._hashed_bytes += count
                if is_json:
                    self._json[key] = immutable(json.loads(data, object_pairs_hook=object_pairs,
                                                         parse_constant=core._constant))
                    self._parses += 1
                    self._json_bytes += count
                    del data
                self._captures[key] = HashCapture(key, actual, count)
            capture = self._captures[key]
            require(capture.sha256 == expected, 'Endpoint expected SHA conflict')
            require(self._resolver._resolve(path) == (endpoint, path_id, endpoint_id),
                    'Path changed during capture')
            self._resolver._guards[name] = path_id
            self._resolver._guards[key] = endpoint_id
            self._visited.add(name)
            return capture
        except Exception:
            self._failed = True
            raise

    def sha(self, path):
        """Compatibility digest: only known pins; no fresh-live-content claim."""
        self._active()
        try:
            name = str(core._path(path))
            return self._capture(path, self.pins.get(name)).sha256
        except Exception:
            self._failed = True
            raise

    digest = sha

    def pin(self, destination, path, expected=None):
        """Destination pin membership remains exact; conflicting writes reject."""
        self._active()
        try:
            path = core._path(path)
            name = str(path)
            authority = self.pins.get(name)
            require(authority is not None and expected in (None, authority), 'Pin lacks exact authority')
            require(destination.get(name, authority) == authority, 'Destination pin conflict')
            self._capture(path, authority)
            destination[name] = authority
            return path
        except Exception:
            self._failed = True
            raise

    def load_sealed(self, path, seal):
        self._active()
        try:
            name = str(core._path(path))
            binding = self._resolver._aliases.get(name)
            endpoint = binding.resolved if binding else name
            require(endpoint in self._json_endpoints, 'JSON was not declared before capture')
            capture = self._capture(path, seal)
            return self._json[capture.endpoint]
        except Exception:
            self._failed = True
            raise

    def read_config(self, output, seal, validator):
        """Same reader reference reaches validator; this is not a legacy bypass."""
        self._active()
        try:
            config = self.load_sealed(core._path(output) / 'config.json', seal)
            require(isinstance(config, MappingProxyType), 'Config must be JSON object')
            verdict = validator(config, core._path(output), self)
            require(verdict is not False, 'Validator explicitly rejected config')
            return self, config
        except Exception:
            self._failed = True
            raise

    def namespace(self):
        return dict(sha=self.sha, pin=self.pin, load_sealed=self.load_sealed)

    def check_pins(self, pins):
        self._active()
        try:
            require(dict(pins) == dict(self.pins), 'Exact all-path pin inventory required')
            for path, expected in pins.items():
                self._capture(path, expected)
        except Exception:
            self._failed = True
            raise

    def finish(self):
        self._active()
        try:
            require(self._visited == set(self.pins), 'Unverified path obligations remain')
            for path in self.pins:
                self._resolver._resolve(Path(path))
            return self.statistics
        except Exception:
            self._failed = True
            raise

    @property
    def statistics(self):
        return MappingProxyType(dict(reads=self._reads, hashes=self._reads,
            hashed_bytes=self._hashed_bytes, parses=self._parses,
            json_input_bytes=self._json_bytes, retained_raw_bytes=0,
            verified_paths=len(self._visited)))

    def close(self):
        self._closed = True
        self._captures.clear()
        self._json.clear()
        self._resolver.close()
