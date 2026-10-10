"""735 constant-Path bridge and measured read roles; no frozen module changes."""
from pathlib import Path
from types import FunctionType, SimpleNamespace

import eight_policy_epoch_735_report_v4 as prior
import eight_policy_epoch_732_report_v4 as bridge

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v5.py')
ROOT = prior.ROOT
PLAN = 'epoch-readiness-735-v5-plan.json'
AUDIT = ROOT / 'host-byte-role-audit-v5.json'
require = prior.require


def constant_inventory(owner, context):
    """Inventory only namespaces known to be private to this owner."""
    namespaces = {}
    methods = []
    for cls in type(context).__mro__:
        methods.extend(v for v in vars(cls).values() if isinstance(v, FunctionType))
    for name in ('frozen', 'fixed', 'eight', 'six', 'shared', 'runner'):
        facade = getattr(owner, name, None)
        if facade is not None:
            methods.extend(v for v in vars(facade).values() if isinstance(v, FunctionType))
    for function in methods:
        namespace = function.__globals__
        if namespace.get('Path') is owner.Path:
            namespaces.setdefault(id(namespace), (namespace, set()))[1].add(function.__name__)
    rows = []
    for namespace, functions in namespaces.values():
        for name, value in namespace.items():
            if isinstance(value, Path):
                rows.append(dict(functions=sorted(functions), constant=name, literal=str(value),
                                 snapshot_member=False))
            elif name == 'snapshot':
                for member, item in vars(value).items():
                    if isinstance(item, Path):
                        rows.append(dict(functions=sorted(functions), constant='snapshot.'+member,
                                         literal=str(item), snapshot_member=True))
    return rows, methods


def bind_owner_paths(owner):
    rows, methods = constant_inventory(owner, owner.context)
    proxy = SimpleNamespace(Path=owner.Path, frozen=SimpleNamespace(**{
        'function_'+str(i): function for i, function in enumerate(methods)
        if function.__globals__.get('Path') is owner.Path}))
    bridge.bind_constant_paths(proxy, owner.context)
    for function in methods:
        namespace = function.__globals__
        if namespace.get('Path') is owner.Path:
            require(all(not isinstance(v, Path) or isinstance(v, owner.Path) for v in namespace.values()),
                    'Unbound private Path constant')
            if 'snapshot' in namespace:
                require(all(not isinstance(v, Path) or isinstance(v, owner.Path)
                            for v in vars(namespace['snapshot']).values()), 'Unbound private snapshot Path')
    owner.constant_path_inventory = rows


class Wiring(prior.prior.Wiring):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bind_owner_paths(self)

    def enter(self, phase):
        super().enter(phase)
        if self.context is not None:
            bind_owner_paths(self)


class DiagnosticWiring(Wiring):
    def enter(self, phase):
        prior.diagnostic_enter(self, phase)
        if self.context is not None:
            bind_owner_paths(self)


def clone_functions(module, **overrides):
    values = dict(vars(module), **overrides)
    for name, function in vars(module).items():
        if name not in overrides and isinstance(function, FunctionType) and function.__globals__ is vars(module):
            clone = FunctionType(function.__code__, values, name, function.__defaults__, function.__closure__)
            clone.__kwdefaults__ = function.__kwdefaults__
            values[name] = clone
    return SimpleNamespace(**values)


def dependencies():
    return tuple(dict.fromkeys((*prior.prior.dependencies(), prior.SCRIPT, prior.TEST,
        Path(bridge.__file__).resolve(), Path(bridge.__file__).with_name('test_eight_policy_epoch_732_report_v4.py'),
        SCRIPT, TEST, AUDIT)))


# Reuse the original audit/restriction bodies in a private namespace. The
# source735-v3 seal stays fixed; neither the failed v4 nor its modules mutate.
local = clone_functions(prior, SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN, AUDIT=AUDIT,
    DiagnosticWiring=DiagnosticWiring, dependencies=dependencies)
formal_wiring = prior.prior.prior.clone(prior.prior.wiring, Wiring=Wiring)
report = prior.prior.prior.clone(prior.report, wiring=formal_wiring,
    PLAN=PLAN, SCRIPT=SCRIPT, TEST=TEST, dependencies=dependencies, save=local.save,
    family=prior.report.family)
for function in vars(local).values():
    if isinstance(function, FunctionType) and function.__globals__.get(function.__name__) is function:
        function.__globals__['report'] = report
        function.__globals__['AUDIT_SEAL'] = None
local.report = report


def main():
    local.main()


if __name__ == '__main__':
    main()
