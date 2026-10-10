"""Immutable successor: large historical JSON is hash-only unless actually consumed."""
from pathlib import Path
from types import FunctionType

import eight_policy_epoch_732_report as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_732_report_v2.py')
PLAN = 'epoch-readiness-v2-plan.json'
SMALL_JSON = 32 * 1024 * 1024


def dependencies():
    return (*prior.dependencies(), SCRIPT, TEST)


def restrict_roles(value):
    """Remove read capabilities only; every original exact pin remains mandatory."""
    output = Path(value['output'])
    builder = prior.Builder()
    fixed = builder.load_sealed(output / prior.wiring.fixed.PLAN, value['fixed_seal'])
    eight = Path(fixed['eight_output'])
    runtime = builder.load_sealed(eight / 'runtime-plan.json', fixed['eight_seal'])
    six = Path(runtime['six_output'])
    required = {str(p) for p in (output / 'config.json', eight / 'config.json', six / 'config.json',
                prior.wiring.population.frozen.QUALIFIED707 / 'config.json',
                prior.wiring.population.frozen.BASE / 'config.json')}
    result = dict(value)
    result['byte_paths'] = [p for p in value['byte_paths'] if
        not p.endswith('.json') or p in required or Path(p).stat().st_size <= SMALL_JSON]
    result['json_paths'] = [p for p in value['json_paths'] if p in result['byte_paths']]
    result['large_json_read_authorities'] = sorted(required)
    result['hash_only_large_json'] = sorted(set(value['json_paths']) - set(result['json_paths']))
    prior.require(result['pins'] == value['pins'], 'Role restriction changed SHA obligations')
    return result


def save(path, value):
    return prior.save(path, restrict_roles(value) if path.name == PLAN else value)


namespace = dict(vars(prior), SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN,
                 dependencies=dependencies, save=save)
for name, function in vars(prior).items():
    if name not in ('dependencies', 'save') and isinstance(function, FunctionType) and function.__module__ == prior.__name__:
        namespace[name] = FunctionType(function.__code__, namespace, name,
                                       function.__defaults__, function.__closure__)
globals().update({name: value for name, value in namespace.items() if not name.startswith('__')
                  and name not in ('prior', 'Path', 'FunctionType')})


if __name__ == '__main__':
    main()
