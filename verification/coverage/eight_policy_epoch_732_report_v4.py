"""Private constant-Path binding successor; original modules remain unchanged."""
from pathlib import Path
from types import FunctionType, SimpleNamespace

import eight_policy_epoch_732_report_v3 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_732_report_v4.py')
PLAN = 'epoch-readiness-v4-plan.json'


def bind_constant_paths(owner, context):
    namespaces = {}
    for cls in type(context).__mro__:
        for value in vars(cls).values():
            if isinstance(value, FunctionType) and value.__globals__.get('Path') is owner.Path:
                namespaces[id(value.__globals__)] = value.__globals__
    for value in vars(owner.frozen).values():
        if isinstance(value, FunctionType) and value.__globals__.get('Path') is owner.Path:
            namespaces[id(value.__globals__)] = value.__globals__
    for namespace in namespaces.values():
        for name, value in tuple(namespace.items()):
            if isinstance(value, Path):
                namespace[name] = owner.Path(value)
        if 'snapshot' in namespace:
            original = namespace['snapshot']
            namespace['snapshot'] = SimpleNamespace(**{name: owner.Path(value) if isinstance(value, Path)
                else value for name, value in vars(original).items()})
    return context


def context_factory(owner):
    return bind_constant_paths(owner, prior.wiring.source_context732(owner))


class PrivateWiring(prior.PrivateWiring):
    def __init__(self, *args, context_factory=None, **kwargs):
        super().__init__(*args, context_factory=context_factory or globals()['context_factory'], **kwargs)


def dependencies():
    return (*prior.dependencies(), SCRIPT, TEST)


private_wiring = SimpleNamespace(**dict(vars(prior.wiring), Wiring=PrivateWiring))
namespace = dict(vars(prior), SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN,
                 dependencies=dependencies, wiring=private_wiring)
for name, function in vars(prior).items():
    if name != 'dependencies' and isinstance(function, FunctionType) and function.__globals__ is prior.namespace:
        namespace[name] = FunctionType(function.__code__, namespace, name,
                                       function.__defaults__, function.__closure__)
globals().update({name: value for name, value in namespace.items() if not name.startswith('__')
                  and name not in ('prior', 'Path', 'FunctionType', 'PrivateWiring', 'context_factory',
                                  'bind_constant_paths', 'private_wiring')})


if __name__ == '__main__':
    main()
