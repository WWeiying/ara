"""One-shot reviewed seven-policy lifecycle; preparation never launches EDA."""
import json
from pathlib import Path
from types import FunctionType

import run_six_policy_population as prior
import lzc_selector_native_seven_policy_runtime as generic

frozen, require = generic.frozen, generic.require
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_lzc_selector_native_seven_policy.py')

# Preserve the frozen exclusive claim, background handshake and PID consumer rules.
for _name, _value in vars(prior).items():
    if isinstance(_value, FunctionType) and _value.__module__ == prior.__name__:
        globals()[_name] = FunctionType(_value.__code__, globals(), _name,
                                       _value.__defaults__, _value.__closure__)
    elif not _name.startswith('__') and _name not in ('generic', 'SCRIPT', 'TEST'):
        globals().setdefault(_name, _value)


def prepare_entry(output, config_seal):
    output = output_path(output)
    require(not (output / PLAN).exists(), 'Launch entry already sealed')
    unstarted(output)
    _, config = generic.read_config(output, config_seal)
    runtime = frozen.load_sealed(output / 'runtime-plan.json', config_seal)
    pins = dict(config['pins'])
    for path in (SCRIPT, TEST, Path(generic.__file__).resolve(), generic.TCL,
                 output / 'runtime-plan.json', Path(prior.__file__).resolve()):
        actual = frozen.sha(path)
        require(str(path) not in pins or pins[str(path)] == actual, 'Launch dependency drift')
        pins[str(path)] = actual
    record = dict(schema='lzc-seven-policy-single-launch-v1', output=str(output),
                  config_sha256=config_seal, config_role='runtime-plan.json; config.json is unchanged six-view facade',
                  admission_manifest_sha256=runtime['admission_sha256'], population=runtime['population'],
                  targets=5868, protected=17702, audited=23570, command=config['command'],
                  timeout_seconds=frozen.TIMEOUT, lifecycle_source=str(frozen.SCRIPT),
                  lifecycle='private frozen.run/read_config/verify adapter',
                  config_reprepared=False, automatic_retry=False, launch_approved=False,
                  parent_review_required=True, application_approval=False, pins=pins)
    frozen.write(output / PLAN, record)
    frozen.write(output / 'population-launch-plan.sha256.json', {str(output / PLAN): frozen.sha(output / PLAN)})
    return record


def reviewed_entry(output, launch_seal):
    output = output_path(output)
    plan = frozen.load_sealed(output / PLAN, launch_seal)
    require(plan['schema'] == 'lzc-seven-policy-single-launch-v1' and plan['output'] == str(output)
            and not plan['config_reprepared'] and not plan['automatic_retry']
            and not plan['launch_approved'] and plan['parent_review_required']
            and not plan['application_approval']
            and (plan['targets'], plan['protected'], plan['audited'], plan['timeout_seconds']) ==
            (5868, 17702, 23570, frozen.TIMEOUT), 'Reviewed seven launch contract differs')
    for path, expected in plan['pins'].items():
        require(frozen.sha(path) == expected, 'Launch pin drift: ' + path)
    context, config = generic.read_config(output, plan['config_sha256'])
    require(plan['population'] == config['population']
            and plan['admission_manifest_sha256'] == config['admission_manifest_sha256']
            and plan['command'] == config['command']
            and all(plan['pins'].get(p) == h for p, h in config['pins'].items()), 'Launch input/command mismatch')
    for path in (SCRIPT, TEST, Path(generic.__file__).resolve(), generic.TCL,
                 output / 'runtime-plan.json', Path(prior.__file__).resolve()):
        require(plan['pins'].get(str(path)) == frozen.sha(path), 'Unpinned actual seven entry')
    return plan, context, config


def invoke_run(output, plan, context, config):
    def read_adapter(path, seal):
        require(path == output and seal == plan['config_sha256'], 'Run identity differs')
        _, actual = generic.read_config(path, seal)
        require(actual == config, 'Runtime configuration drift')
        return actual

    def verify_adapter(path, actual):
        require(path == output and actual == config, 'Verifier runtime identity differs')
        return generic.verify(path, plan['config_sha256'])

    bindings = dict(context.namespace(), read_config=read_adapter, verify_artifacts=verify_adapter)
    generic.six.private(frozen.run, **bindings)(output, plan['config_sha256'])


if __name__ == '__main__':
    main()
