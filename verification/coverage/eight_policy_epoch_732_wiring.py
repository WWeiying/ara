"""Private eight-policy732 wiring. No prepare/launch CLI and no frozen mutations.

The frozen CSV/eight validators and foreground lifecycle remain function bodies
in private namespaces. Each integrity phase gets a new capture store. Expected
pins and byte/JSON roles must be supplied by a reviewed future732 config; this
module does not discover authority from file contents or relabel a729 config.
"""
import builtins
from collections.abc import Mapping
import hashlib
import io
import json
import math
import os
from pathlib import Path, PosixPath
from types import FunctionType, SimpleNamespace

import prepare_six_policy_population as population
import prepare_six_policy_population_729 as identity
import lzc_snapshot_eight_policy_runtime as eight
import eight_policy_csv_fix_runtime as fixed
import run_eight_policy_csv_fix as runner
import capture_operand_1144 as lifecycle
from population_reader_732_consumer import LINKS, path_binding
import population_reader_732 as root732
from verification_epoch import EpochError, _identity, _sha

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_732_wiring.py')


def require(value, message):
    if not value:
        raise EpochError(message)


def deny(*args, **kwargs):
    raise EpochError('Captured JSON is immutable')


class FrozenDict(dict):
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = deny

    def __deepcopy__(self, memo):
        return self


class FrozenList(list):
    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = sort = reverse = deny
    __iadd__ = __imul__ = deny

    def __deepcopy__(self, memo):
        return self


def freeze_lists(value):
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, list):
        return FrozenList(freeze_lists(item) for item in value)
    if isinstance(value, float):
        require(math.isfinite(value), 'Nonfinite JSON number')
    return value


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key')
        result[key] = freeze_lists(value)
    return FrozenDict(result)


def nonfinite(value):
    raise EpochError('Nonfinite JSON constant')


def clone(module, **bindings):
    namespace = dict(vars(module), **bindings)
    for name, value in vars(module).items():
        if name not in bindings and isinstance(value, FunctionType) and value.__module__ == module.__name__:
            namespace[name] = FunctionType(value.__code__, namespace, name, value.__defaults__, value.__closure__)
    return SimpleNamespace(**namespace)


def facade_copy(value, *args):
    require(isinstance(value, (dict, FrozenDict)), 'Only explicit top-level dictionary facade allowed')
    return dict(value)


class CapturePhase:
    """One exact-pin evaluation. Binary tools stream; declared bytes are bounded."""

    def __init__(self, pins, byte_paths, json_paths, links, *, max_bytes=768 * 1024 * 1024):
        require(type(max_bytes) is int and max_bytes > 0, 'Positive explicit byte budget required')
        self.pins = dict(pins)
        self.byte_paths, self.json_paths = set(byte_paths), set(json_paths)
        require(self.json_paths <= self.byte_paths <= set(self.pins), 'All byte/JSON roles must be pinned')
        self.links = dict(links)
        self.bindings, authorities = {}, {}
        for name, expected in self.pins.items():
            _sha(expected)
            # The exact literal comes from the supplied sealed pin inventory.
            # Every dot-dot step still has to cross an ordinary directory.
            prefix = name.rsplit('/', 1)[0] + '/' if name != os.path.normpath(name) else None
            binding = path_binding(name, self.links, prefix)
            require(authorities.get(binding[0], expected) == expected, 'Endpoint authority conflict')
            authorities[binding[0]] = expected
            self.bindings[name] = binding
        self.byte_endpoints = {self.bindings[p][0] for p in self.byte_paths}
        self.json_endpoints = {self.bindings[p][0] for p in self.json_paths}
        self.limit = max_bytes
        self.raw, self.parsed, self.captures, self.endguards = {}, {}, {}, {}
        self.buffers, self.visited, self.headers = {}, set(), {}
        self.texts = {}
        self.retained = self.reads = self.hashes = self.parses = 0
        self.failed = False

    def guard(self, value, message):
        if not value:
            self.failed = True
            raise EpochError(message)

    def capture(self, name, expected=None):
        try:
            require(not self.failed, 'Capture phase failed')
            name = os.fspath(name)
            require(name in self.pins and expected in (None, self.pins.get(name)), 'Unknown/conflicting pin')
            prefix = name.rsplit('/', 1)[0] + '/' if name != os.path.normpath(name) else None
            binding = path_binding(name, self.links, prefix)
            require(binding == self.bindings[name], 'Literal path identity changed')
            endpoint = binding[0]
            info = _identity(os.stat(endpoint, follow_symlinks=False))
            if endpoint in self.captures:
                require(self.endguards[endpoint] == info, 'Endpoint metadata changed')
            else:
                retain = endpoint in self.byte_endpoints
                require(not retain or self.retained + info[3] <= self.limit, 'Byte capture budget exceeded')
                data = bytearray() if retain else None
                digest = hashlib.sha256()
                count = 0
                header = b''
                with os.fdopen(os.open(endpoint, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
                    require(_identity(os.fstat(stream.fileno())) == info, 'Changed before capture')
                    while True:
                        block = stream.read(1024 * 1024)
                        if not block:
                            break
                        if count == 0:
                            header = block[:4]
                        count += len(block)
                        require(count <= info[3], 'File grew during capture')
                        digest.update(block)
                        if retain:
                            data.extend(block)
                    require(_identity(os.fstat(stream.fileno())) == info, 'Changed during capture')
                actual = digest.hexdigest()
                require(count == info[3] and actual == self.pins[name], 'Expected SHA differs')
                self.reads += 1
                self.hashes += 1
                if retain:
                    payload = bytes(data)
                    self.raw[endpoint] = payload
                    self.retained += len(payload)
                    self.buffers[id(payload)] = (payload, endpoint)
                self.captures[endpoint] = actual
                self.endguards[endpoint] = info
                self.headers[endpoint] = header
            require(path_binding(name, self.links, prefix) == binding and
                    _identity(os.stat(endpoint, follow_symlinks=False)) == info, 'Changed after capture')
            self.visited.add(name)
            return endpoint
        except Exception:
            self.failed = True
            raise

    def sha(self, path):
        return self.captures[self.capture(path)]

    def bytes(self, path):
        endpoint = self.capture(path)
        self.guard(endpoint in self.byte_endpoints, 'Undeclared byte read; no second read allowed')
        return self.raw[endpoint]

    def text(self, path, encoding='utf-8', errors='strict'):
        self.guard(encoding in (None, 'utf-8', 'UTF-8') and errors in (None, 'strict'), 'Only strict UTF8 evidence text')
        data = self.bytes(path)
        endpoint = self.bindings[os.fspath(path)][0]
        if endpoint not in self.texts:
            try:
                value = data.decode('utf-8')
            except UnicodeError:
                self.failed = True
                raise
            self.texts[endpoint] = value
            self.buffers[id(value)] = (value, endpoint)
        return self.texts[endpoint]

    def loads(self, data, *args, **kwargs):
        self.guard(not self.failed and not args and not kwargs, 'Failed phase/unreviewed JSON parser options')
        record = self.buffers.get(id(data))
        self.guard(record is not None and record[0] is data and record[1] in self.json_endpoints,
                'JSON must consume declared captured bytes')
        endpoint = record[1]
        if endpoint not in self.parsed:
            try:
                self.parsed[endpoint] = freeze_lists(json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite))
                self.parses += 1
            except Exception:
                self.failed = True
                raise
        return self.parsed[endpoint]

    def load_sealed(self, path, expected):
        self.capture(path, _sha(expected))
        return self.loads(self.bytes(path))

    def pin(self, destination, path, expected=None):
        endpoint = self.capture(path, expected)
        name = os.fspath(path)
        actual = self.captures[endpoint]
        self.guard(destination.get(name, actual) == actual, 'Destination pin conflict')
        if name not in destination:
            self.guard(not isinstance(destination, FrozenDict), 'Immutable config omitted required pin')
            destination[name] = actual
        return Path(name)

    def check_pins(self, pins):
        for path, expected in pins.items():
            self.capture(path, _sha(expected))

    def finish(self):
        self.guard(not self.failed and self.visited == set(self.pins), 'Incomplete capture phase')
        for path in self.pins:
            self.capture(path)
        return dict(reads=self.reads, hashes=self.hashes, parses=self.parses,
                    retained_bytes=self.retained, verified_literal_paths=len(self.visited))


class Wiring:
    """Actual frozen reader/lifecycle family; source Context must be reviewed.

    context_factory receives this wiring and must return a real population
    Context bound to exact732. It may not substitute an empty check_config.
    No default constructor accepts729 identity as732. A complete source Context
    adapter is deliberately a prerequisite, not an implicit waived gate.
    """

    def __init__(self, pins, byte_paths, json_paths, context_factory=None, *, links=None,
                 max_bytes=768 * 1024 * 1024):
        self.pins = dict(pins)
        self.byte_paths, self.json_paths = tuple(byte_paths), tuple(json_paths)
        tool_links = dict(identity.LINKS)
        tool_links[str(identity.SCRIPT.parents[2] / 'install')] = '/home/wangwy/openproject/ara/install'
        self.links = dict(LINKS, **tool_links, **(links or {}))
        self.factory, self.max_bytes = context_factory or source_context732, max_bytes
        self.phase_name = None
        self.phase = None
        self.context = None
        self.history = []
        self.enter('pre')
        owner = self

        class BoundPath(PosixPath):
            def read_bytes(self):
                return owner.phase.bytes(str(self))

            def read_text(self, encoding=None, errors=None):
                return owner.phase.text(str(self), encoding, errors)

            def open(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
                require(mode in ('r', 'rb'), 'Private validator may only read captured files')
                raw = io.BytesIO(owner.phase.bytes(str(self)))
                return raw if mode == 'rb' else io.TextIOWrapper(raw, encoding=encoding or 'utf-8',
                    errors=errors or 'strict', newline=newline)

        self.Path = BoundPath
        self.json = SimpleNamespace(**dict(vars(json), loads=lambda *a, **k: self.phase.loads(*a, **k)))
        self.copy = SimpleNamespace(deepcopy=facade_copy)
        self.shared = clone(fixed.shared, check_pins=lambda pins: self.phase.check_pins(pins))
        class HeaderPath(PosixPath):
            def open(self, mode='r', *args, **kwargs):
                require(mode == 'rb' and not args and not kwargs, 'Tool probe only permits ELF header read')
                endpoint = owner.phase.capture(str(self))
                return io.BytesIO(owner.phase.headers[endpoint])

        def seal_tool(path):
            path = Path(path).absolute()
            before = lifecycle.tool.identity(path)
            actual = self.phase.sha(path)
            require(lifecycle.tool.identity(path) == before, 'Tool identity changed during validation')
            return dict(path=str(path), identity=before, sha256=actual)

        self.tool = clone(lifecycle.tool, Path=HeaderPath, seal_file=seal_tool)
        phase_lifecycle = clone(lifecycle, tool=self.tool,
                                check_inputs=lambda cfg: self.check_inputs(cfg))
        original_import = builtins.__import__

        def source_import(name, *args, **kwargs):
            return phase_lifecycle if name == 'capture_operand_1144' else original_import(name, *args, **kwargs)

        self.frozen = clone(population.frozen, Path=BoundPath, json=self.json, copy=self.copy,
            sha=lambda p: self.phase.sha(p), pin=lambda *a: self.phase.pin(*a),
            load_sealed=lambda p, s: self.phase.load_sealed(p, s),
            __builtins__=dict(vars(builtins), __import__=source_import))
        self.six = SimpleNamespace(**dict(vars(population), read_config=self.read_six,
                                         frozen=self.frozen, private=population.private))
        self.eight = clone(eight, Path=BoundPath, json=self.json, copy=self.copy,
                           frozen=self.frozen, six=self.six)
        self.fixed = clone(fixed, Path=BoundPath, json=self.json, copy=self.copy,
                           frozen=self.frozen, shared=self.shared, six=self.six, eight=self.eight)
        self.runner = clone(runner, Path=BoundPath, json=self.json, frozen=self.frozen,
                            generic=self.fixed, invoke_run=self.invoke_run)
        self.context = self.factory(self)
        self._check_context()

    def _check_context(self):
        require(isinstance(self.context, population.Context) and
                self.context.admission == root732.ADMISSION and self.context.seal == root732.SEAL and
                type(self.context.population) is int and self.context.population == 732,
                'Reviewed exact732 source Context required; never relabel729')
        require(self.context.check_config.__func__.__code__ is population.Context.check_config.__code__,
                'Original complete source/native Context check_config body required')

    def enter(self, phase):
        require((self.phase_name, phase) in ((None, 'pre'), ('pre', 'live'), ('live', 'post')),
                'Integrity boundary skipped/reused/out of order')
        self.phase = CapturePhase(self.pins, self.byte_paths, self.json_paths, self.links, max_bytes=self.max_bytes)
        self.phase_name = phase
        self.history.append(phase)
        if self.context is not None:
            self.context = self.factory(self)
            self._check_context()

    def read_six(self, output, seal):
        try:
            config = self.phase.load_sealed(output / 'config.json', seal)
            require(config['population'] == 732 and config['admission_manifest_sha256'] == root732.SEAL,
                    'Exact732 six reader population/seal required')
            facade = dict(config)
            facade['pins'] = dict(config['pins'])
            self.context.check_config(facade, output)
            require(facade == config, 'Source validator changed sealed config/pins')
            return self.context, config
        except Exception:
            self.phase.failed = True
            raise

    def check_inputs(self, config, *, boundary=None):
        if boundary is not None:
            self.enter(boundary)
        self.phase.check_pins(config['pins'])
        # Preserve actual tree membership and actual tool revalidation. These
        # are fresh boundary checks, never inferred from a previous capture.
        for root, members in config['plan']['input_membership'].items():
            require(lifecycle.proof.tree_members(root) == members, 'Input tree membership changed')
        self.tool.revalidate(config['plan']['tool_identity'])

    def invoke_run(self, output, plan, context, config):
        # Generated DVE artifacts need a separate, finite post-run authority
        # adapter. This reader-only wiring must not launch without it.
        require(False, 'Reader integration only: generated-evidence authority not implemented; no launch')
        require(self.phase_name == 'pre', 'Only pre phase may launch')
        boundary_calls = []

        def checkpoint(actual):
            boundary = 'live' if not boundary_calls else 'post'
            require(len(boundary_calls) < 2, 'Unexpected lifecycle integrity checkpoint')
            self.check_inputs(actual, boundary=boundary)
            boundary_calls.append(boundary)

        bridge = clone(lifecycle, tool=self.tool, check_inputs=checkpoint)
        original_import = builtins.__import__

        def local_import(name, *args, **kwargs):
            return bridge if name == 'capture_operand_1144' else original_import(name, *args, **kwargs)

        def read_adapter(path, seal):
            require(path == output and seal == plan['config_sha256'], 'Run identity differs')
            _, actual = self.fixed.read_config(path, seal)
            require(actual == config, 'Runtime config changed')
            return actual

        def verify_adapter(path, actual):
            require(boundary_calls == ['live', 'post'] and path == output and actual == config,
                    'Verifier requires both fresh integrity boundaries')
            return self.fixed.verify(path, plan['config_sha256'])

        bindings = dict(context.namespace(), read_config=read_adapter, verify_artifacts=verify_adapter,
                        __builtins__=dict(vars(builtins), __import__=local_import))
        population.private(population.frozen.run, **bindings)(output, plan['config_sha256'])


def private_base_context(wiring):
    """Clone original source/native check methods, not approvals or empty hooks.

    This factory is the base for the mandatory historical producer identity
    adapter. It intentionally cannot approve a config with extra identity fields
    until that adapter reproduces and validates them.
    """
    namespace = dict(vars(population), Path=wiring.Path, json=wiring.json, copy=wiring.copy,
                     frozen=wiring.frozen)
    for name, value in vars(population).items():
        if isinstance(value, FunctionType) and value.__module__ == population.__name__:
            namespace[name] = FunctionType(value.__code__, namespace, name,
                                          value.__defaults__, value.__closure__)
    attrs = {}
    for name, value in vars(population.Context).items():
        if isinstance(value, FunctionType):
            attrs[name] = FunctionType(value.__code__, namespace, name, value.__defaults__, value.__closure__)
    return type('Private732BaseContext', (population.Context,), attrs)


def extended_cc_proof(namespace):
    """Keep original R1 provenance checks; only extend the exact ancestor range."""
    function = identity.cc_ancestry
    constants = function.__code__.co_consts
    require(sum(type(c) is int and c == 729 for c in constants) == 1 and
            sum(type(c) is int and c == 7 for c in constants) == 1,
            'Frozen cc ancestry range/length boundary changed')
    code = function.__code__.replace(co_consts=tuple(
        732 if type(c) is int and c == 729 else 10 if type(c) is int and c == 7 else c
        for c in constants))
    return FunctionType(code, namespace, function.__name__, function.__defaults__, function.__closure__)


def source_context732(wiring):
    """Private complete legacy Context with exact732/ten-ancestor producer pins.

    Missing workspace aliases in732 are bound only through sealed729 ancestry,
    never fabricated as732 top-level entries. The alias-source record is explicit.
    All metadata/byte roles must already be in the reviewed session inventory.
    """
    base = private_base_context(wiring)
    private_population = clone(population, Path=wiring.Path, json=wiring.json,
                               copy=wiring.copy, frozen=wiring.frozen, Context=base)
    private_v2 = clone(identity.v2, Path=wiring.Path, json=wiring.json, frozen=wiring.frozen)
    schemas = dict(identity.SCHEMAS, **{})
    schemas.update({730: 'GAP108_HISTORICAL730_SOFTWARE_NATIVE_ADMISSION_V1',
                    731: 'PURE_WAR_HISTORICAL731_FULL_ARCHITECTURAL_ADMISSION_V1',
                    732: root732.SCHEMA})
    namespace = dict(vars(identity), Path=wiring.Path, json=wiring.json, frozen=wiring.frozen,
                     base=private_population, v2=private_v2, ADMISSION=root732.ADMISSION,
                     ADMISSION_SEAL=root732.SEAL, SCHEMAS=schemas)
    for name, value in vars(identity).items():
        if isinstance(value, FunctionType) and value.__module__ == identity.__name__:
            namespace[name] = FunctionType(value.__code__, namespace, name, value.__defaults__, value.__closure__)
    namespace['cc_ancestry'] = extended_cc_proof(namespace)
    attrs = {name: FunctionType(value.__code__, namespace, name, value.__defaults__, value.__closure__)
             for name, value in vars(identity.Context).items() if isinstance(value, FunctionType)}
    constructor = identity.Context.__init__
    constants = constructor.__code__.co_consts
    require(sum(type(c) is int and c == 729 for c in constants) == 1,
            'Frozen identity constructor population boundary changed')
    constructor_code = constructor.__code__.replace(co_consts=tuple(
        732 if type(c) is int and c == 729 else
        'Only explicitly sealed formal732' if c == 'Only explicitly sealed formal729' else c
        for c in constants))
    attrs['__init__'] = FunctionType(constructor_code, namespace, '__init__',
                                   constructor.__defaults__, constructor.__closure__)
    private_identity_class = type('Private732IdentityContext', (identity.Context, base), attrs)

    class SourceContext(private_identity_class):
        def ledger(self):
            if self._ledger is None:
                _, current = namespace['sealed_ledger'](self.admission, self.seal, {})
                merged = dict(current)
                self.alias_authorities = {}
                for key, spec in identity.ALIASES.items():
                    if key in current:
                        require(current[key] == spec[2], 'Actual732 workspace alias SHA differs')
                        origin, origin_seal = self.admission, self.seal
                    else:
                        # cc_proof verifies the full732->723 chain/prefix first.
                        proof = self.cc_proof()
                        ancestor = [node for node in proof['chain'] if node['population'] == 729]
                        require(len(ancestor) == 1 and ancestor[0]['admission'] == str(identity.ADMISSION) and
                                ancestor[0]['manifest_sha256'] == identity.ADMISSION_SEAL,
                                'Exact sealed729 LLVM alias authority absent')
                        _, old = namespace['sealed_ledger'](identity.ADMISSION, identity.ADMISSION_SEAL, {})
                        require(old.get(key) == spec[2], 'Ancestor workspace alias SHA differs')
                        merged[key] = old[key]
                        origin, origin_seal = identity.ADMISSION, identity.ADMISSION_SEAL
                    self.alias_authorities[key] = dict(admission=str(origin), manifest_sha256=origin_seal,
                        expected_sha256=merged[key], claimed_as_current_top_level=key in current)
                self._ledger = merged
            return self._ledger

        def qualification(self, pins=None):
            qualified = population.private(wiring.frozen.qualification707,
                sha=self.digest, pin=self.pin, load_sealed=wiring.phase.load_sealed)()
            mapped = {}
            for path, expected in qualified['pins'].items():
                self.pin(mapped, path, expected)
            # Only the changed top-level pin facade is mutable; policies share
            # the original immutable parsed groups/bindings.
            facade = dict(qualified)
            facade['pins'] = mapped
            if pins is not None:
                for path, expected in mapped.items():
                    require(pins.get(path, expected) == expected, 'Qualification destination conflict')
                    if path not in pins:
                        pins[path] = expected
            return facade

        def source_binding(self, pins):
            result = super().source_binding(pins)
            result['workspace_llvm732'] = result.pop('workspace_llvm729')
            result['workspace_llvm_alias_authority'] = self.alias_authorities
            result['identity_population'] = 732
            catalog = {}
            ledger = self.ledger()
            for link in population.frozen.INHERITED_TOOL_LINKS:
                item = namespace['tool_link_identity'](link)
                endpoint = item['resolved']
                authority = link if link in ledger else endpoint
                expected = ledger.get(authority)
                require(expected == item['sha256'], 'Original catalog lacks sealed endpoint authority')
                self.pin(pins, link, expected)
                self.pin(pins, endpoint, expected)
                require(pins.get(link) == pins.get(endpoint) == expected, 'Incomplete catalog pair')
                catalog[link] = dict(item, ledger_authority=authority,
                                    historical_alias_invocation_claim=False)
            result['original_catalog_endpoint_binding'] = catalog
            for path in (SCRIPT, TEST):
                self.pin(pins, path)
            result['private_epoch_wiring'] = {str(p): self.digest(p) for p in (SCRIPT, TEST)}
            return result

    return SourceContext(root732.ADMISSION, root732.SEAL, 732)
