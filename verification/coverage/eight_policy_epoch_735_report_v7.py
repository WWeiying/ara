"""Private735 local-helper Path closure; frozen sources and v6 seals unchanged."""
import ast
import inspect
from pathlib import Path
import sys
import textwrap
from types import CodeType, FunctionType, ModuleType, SimpleNamespace

import eight_policy_epoch_735_report_v6 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v7.py')
ROOT = prior.ROOT
PLAN = 'epoch-readiness-735-v7-plan.json'
AUDIT = ROOT / 'host-byte-role-audit-v7.json'
require = prior.require
DESIGN_DB = ROOT.parent / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
COMPILED_READS = tuple(DESIGN_DB / name for name in (
    'design/verilog.design.xml', 'auxiliary/verilog.sourceinfo.xml',
    *(f'shape/{metric}.verilog.{kind}.xml' for metric in ('line', 'branch', 'tgl', 'cond')
      for kind in ('shape', 'info'))))


def read_roles(pins, byte_paths, json_paths):
    require(all(str(p) in pins for p in COMPILED_READS), 'Missing historical compiled read authority')
    return sorted(set(byte_paths) | {str(p) for p in COMPILED_READS}), json_paths


def source_plan():
    value = prior.source_plan()
    byte_paths, json_paths = read_roles(value['pins'], value['byte_paths'], value['json_paths'])
    return dict(value, byte_paths=byte_paths, json_paths=json_paths)


def local_file(name):
    return isinstance(name, str) and Path(name).is_relative_to(SCRIPT.parent)


def code_names(code):
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(code_names(value))
    return names


def simple_sha(function):
    """Only a pure file SHA256 expression can use the streaming pin primitive."""
    if function.__name__ not in ('sha', 'digest'):
        return False
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    node = tree.body[0]
    if not isinstance(node, ast.FunctionDef) or len(node.args.args) != 1 or len(node.body) != 1:
        return False
    arg = node.args.args[0].arg
    expected = ast.parse('return hashlib.sha256(Path(%s).read_bytes()).hexdigest()' % arg).body[0]
    return ast.dump(node.body[0]) == ast.dump(expected)


class PathClosure:
    """Clone local helper namespaces, never mutate imported modules or classes.

    The graph is conservative: all names used by each reachable local helper
    function (including nested code objects) are considered. It is not a claim
    that every potential CLI or launch helper was actually called.
    """
    def __init__(self, owner):
        self.owner = owner
        self.namespaces, self.facades, self.functions, self.classes = {}, {}, {}, {}
        self.rows = []
        self.preferred = {}
        for name in ('frozen', 'eight', 'fixed', 'six', 'shared', 'runner'):
            obj = getattr(owner, name)
            self.preferred.setdefault(vars(obj).get('__name__'), obj)

    def constants(self, value, name, paths, active=None):
        if isinstance(value, Path):
            paths.append(dict(name=name, literal=str(value)))
            return self.owner.Path(value)
        if type(value) not in (dict, list, tuple):
            return value
        active = set() if active is None else active
        if id(value) in active:
            return value
        active.add(id(value))
        if type(value) is dict:
            pairs = [(self.constants(k, name + '.key', paths, active),
                      self.constants(v, name + '[' + repr(k) + ']', paths, active))
                     for k, v in value.items()]
            changed = any(a is not k or b is not v for (a, b), (k, v) in zip(pairs, value.items()))
            result = dict(pairs) if changed else value
        else:
            items = [self.constants(v, name + '[' + str(i) + ']', paths, active)
                     for i, v in enumerate(value)]
            result = type(value)(items) if any(a is not b for a, b in zip(items, value)) else value
        active.remove(id(value))
        return result

    def namespace(self, original, label, private=False):
        key = id(original)
        if key in self.namespaces:
            return self.namespaces[key]
        # Already-private method namespaces may be patched; original globals may not.
        result = original if private else dict(original)
        self.namespaces[key] = result
        self.namespaces[id(result)] = result
        module = original.get('__name__', label)
        source = original.get('__file__', '')
        row = dict(namespace=module, entry=label, source=source, private_existing=private,
                   paths=[], functions=[], classes=[], streaming_hash_functions=[])
        self.rows.append(row)
        result['Path'] = self.owner.Path
        if 'json' in result:
            result['json'] = self.owner.json
        used = set()
        for name, value in tuple(original.items()):
            if name not in ('Path', 'json'):
                result[name] = self.constants(value, name, row['paths'])
            if isinstance(value, FunctionType) and value.__globals__.get('__name__') == module:
                used.update(code_names(value.__code__))
                if not private and value.__globals__ is original:
                    if simple_sha(value):
                        result[name] = lambda path: self.owner.phase.sha(path)
                        self.functions[value] = result[name]
                        row['streaming_hash_functions'].append(name)
                    else:
                        result[name] = self.function(value)
                row['functions'].append(name)
        for name in sorted(used):
            if name in result and name not in ('Path', 'json'):
                result[name] = self.value(result[name], module + '.' + name)
        return result

    def function(self, original):
        if original in self.functions:
            return self.functions[original]
        namespace = original.__globals__
        # Retain private owner-bound hooks and closures, including phase SHA/pin.
        module = sys.modules.get(namespace.get('__name__'))
        if module is None or vars(module) is not namespace:
            if namespace.get('Path') is self.owner.Path:
                self.namespace(namespace, original.__qualname__, private=True)
            return original
        if not local_file(original.__code__.co_filename):
            return original
        private = self.namespace(namespace, original.__qualname__)
        if original in self.functions:
            return self.functions[original]
        clone = FunctionType(original.__code__, private, original.__name__,
                             original.__defaults__, original.__closure__)
        clone.__kwdefaults__ = original.__kwdefaults__
        self.functions[original] = clone
        return clone

    def module(self, original, label):
        if id(original) in self.facades:
            return self.facades[id(original)]
        if isinstance(original, ModuleType):
            preferred = self.preferred.get(original.__name__)
            if preferred is not None:
                return self.module(preferred, label)
        facade = SimpleNamespace()
        self.facades[id(original)] = facade
        values = vars(original)
        # Facade functions usually share a different dict than facade.__dict__.
        private_namespaces = {id(f.__globals__): f.__globals__ for f in values.values()
            if isinstance(f, FunctionType) and f.__globals__.get('Path') is self.owner.Path}
        for namespace in private_namespaces.values():
            self.namespace(namespace, label, private=True)
        copied = self.namespace(values, label)
        for name, value in tuple(copied.items()):
            if isinstance(value, FunctionType):
                copied[name] = self.function(value)
        vars(facade).update(copied)
        return facade

    def class_value(self, original, label):
        if original in self.classes:
            return self.classes[original]
        methods = {}
        clone = type(original.__name__, (original,), {'__module__': original.__module__})
        self.classes[original] = clone
        for name, value in vars(original).items():
            if isinstance(value, FunctionType):
                methods[name] = self.function(value)
            elif isinstance(value, (staticmethod, classmethod)):
                methods[name] = type(value)(self.function(value.__func__))
            elif isinstance(value, property):
                methods[name] = property(*(self.function(f) if f else None
                                           for f in (value.fget, value.fset, value.fdel)), doc=value.__doc__)
            elif isinstance(value, Path):
                methods[name] = self.owner.Path(value)
        for name, value in methods.items():
            setattr(clone, name, value)
        return clone

    def value(self, value, label):
        if isinstance(value, (ModuleType, SimpleNamespace)) and local_file(getattr(value, '__file__', None)):
            return self.module(value, label)
        if isinstance(value, FunctionType) and local_file(value.__code__.co_filename):
            return self.function(value)
        if isinstance(value, type) and value.__module__ in sys.modules:
            module = sys.modules[value.__module__]
            if local_file(getattr(module, '__file__', None)):
                return self.class_value(value, label)
        return value

    def install(self):
        for cls in type(self.owner.context).__mro__:
            for method in vars(cls).values():
                if isinstance(method, FunctionType) and method.__globals__.get('Path') is self.owner.Path:
                    self.namespace(method.__globals__, 'context.' + cls.__name__, private=True)
        for name in ('frozen', 'eight', 'fixed', 'six', 'shared', 'runner'):
            setattr(self.owner, name, self.module(getattr(self.owner, name), name))
        for row in self.rows:
            row['paths'].sort(key=lambda p: p['name'])
            for key in ('functions', 'classes', 'streaming_hash_functions'):
                row[key].sort()
        self.owner.path_closure_inventory = sorted(self.rows, key=lambda r: (r['namespace'], r['entry']))
        self.owner.path_closure_classes = [dict(module=c.__module__, name=c.__qualname__,
            methods=sorted(n for n, v in vars(c).items() if isinstance(v, (FunctionType, staticmethod, classmethod, property))))
            for c in sorted(self.classes, key=lambda c: (c.__module__, c.__qualname__))]


class Wiring(prior.Wiring):
    def __init__(self, pins, byte_paths, json_paths, *args, **kwargs):
        byte_paths, json_paths = read_roles(pins, byte_paths, json_paths)
        super().__init__(pins, byte_paths, json_paths, *args, **kwargs)
        PathClosure(self).install()


class DiagnosticWiring(Wiring):
    def enter(self, phase):
        prior.prior.prior.diagnostic_enter(self, phase)
        if self.context is not None:
            prior.prior.bind_owner_paths(self)


def dependencies():
    old_audits = {prior.AUDIT, prior.prior.AUDIT, prior.prior.prior.AUDIT}
    return tuple(dict.fromkeys(p for p in (*prior.dependencies(), SCRIPT, TEST, AUDIT)
                              if p not in old_audits))


local = prior.prior.clone_functions(prior.prior.prior, SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN, AUDIT=AUDIT,
    DiagnosticWiring=DiagnosticWiring, dependencies=dependencies, source_plan=source_plan)


def save(path, value):
    if path.name == PLAN:
        pins, byte_paths, json_paths = prior.closure(value['pins'], value['byte_paths'], value['json_paths'])
        byte_paths, json_paths = read_roles(pins, byte_paths, json_paths)
        value = dict(value, pins=pins, byte_paths=byte_paths, json_paths=json_paths,
                     historical_mask_closure={str(prior.CONFIG): prior.CONFIG_SHA, str(prior.FIRST): prior.FIRST_SHA})
    local.save(path, value)


clone = prior.prior.prior.prior.prior.clone
formal_wiring = clone(prior.prior.prior.prior.wiring, Wiring=Wiring)
report = clone(prior.report, wiring=formal_wiring, PLAN=PLAN, SCRIPT=SCRIPT, TEST=TEST,
               dependencies=dependencies, save=save, family=prior.report.family)
for function in vars(local).values():
    if isinstance(function, FunctionType) and function.__globals__.get(function.__name__) is function:
        function.__globals__['report'] = report
        function.__globals__['AUDIT_SEAL'] = None
local.report = report


if __name__ == '__main__':
    local.main()
