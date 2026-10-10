"""One-shot lifecycle for an already sealed generic six-policy population."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import prepare_six_policy_population as generic

frozen = generic.frozen
require = generic.require
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_six_policy_population.py')
PLAN = 'population-launch-plan.json'
CLAIM = 'population-launch-claim.json'


def output_path(path):
    path = Path(path).absolute()
    require(path.parent == frozen.OUT and path.resolve() == path and not path.is_symlink(),
            'Direct prepared output required')
    return path


def unstarted(output):
    require(json.loads((output / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE',
            'No repeat or failed-run retry')
    require(not any((output / name).exists() for name in
                    (CLAIM, 'live-ready', 'execution.json', 'DVEfiles', 'launcher.log',
                     'population-runner.log', 'population-background.json')),
            'Preexisting run/claim artifacts')


def prepare_entry(output, config_seal):
    output = output_path(output)
    require(not (output / PLAN).exists(), 'Launch entry already sealed')
    unstarted(output)
    _, config = generic.read_config(output, config_seal)
    extra = (SCRIPT, TEST, Path(generic.__file__).resolve(), frozen.SCRIPT,
             output / 'config.json')
    pins = dict(config['pins'])
    for path in extra:
        actual = frozen.sha(path)
        require(str(path) not in pins or pins[str(path)] == actual, 'Dependency drift')
        pins[str(path)] = actual
    record = dict(schema='six-policy-population-single-launch-v1', output=str(output),
                  config_sha256=config_seal, admission_manifest_sha256=config['admission_manifest_sha256'],
                  population=config['population'], targets=config['targets'], protected=config['protected'],
                  command=config['command'], timeout_seconds=config['run_timeout_seconds'],
                  lifecycle_source=str(frozen.SCRIPT), lifecycle='private frozen.run/read_config/verify adapter',
                  config_reprepared=False, automatic_retry=False, launch_approved=False,
                  parent_review_required=True, application_approval=False, pins=pins)
    require(record['targets'] == 5808 and record['protected'] == 13562
            and record['timeout_seconds'] == frozen.TIMEOUT, 'Exact frozen lifecycle bounds required')
    frozen.write(output / PLAN, record)
    frozen.write(output / 'population-launch-plan.sha256.json',
                 {str(output / PLAN): frozen.sha(output / PLAN)})
    require(frozen.sha(output / 'config.json') == config_seal, 'Prepared config changed')
    return record


def reviewed_entry(output, launch_seal):
    output = output_path(output)
    plan = frozen.load_sealed(output / PLAN, launch_seal)
    require(plan['schema'] == 'six-policy-population-single-launch-v1'
            and plan['output'] == str(output) and not plan['config_reprepared']
            and not plan['automatic_retry'] and not plan['launch_approved']
            and plan['parent_review_required'] and not plan['application_approval'],
            'Launch contract changed')
    for path, expected in plan['pins'].items():
        require(frozen.sha(path) == expected, 'Launch dependency drift: ' + path)
    context, config = generic.read_config(output, plan['config_sha256'])
    require((plan['population'], plan['admission_manifest_sha256'], plan['command'],
             plan['timeout_seconds'], plan['targets'], plan['protected']) ==
            (config['population'], config['admission_manifest_sha256'], config['command'],
             config['run_timeout_seconds'], config['targets'], config['protected'])
            and (plan['timeout_seconds'], plan['targets'], plan['protected']) ==
            (frozen.TIMEOUT, 5808, 13562), 'Config/launch identity mismatch')
    require(all(plan['pins'].get(str(path)) == frozen.sha(path) for path in
                (SCRIPT, TEST, Path(generic.__file__).resolve(), frozen.SCRIPT, output / 'config.json')),
            'Actual lifecycle entry not pinned')
    return plan, context, config


def claim_once(output, launch_seal, mode):
    unstarted(output)
    record = dict(launch_plan_sha256=launch_seal, mode=mode, owner_pid=os.getpid(),
                  output=str(output), retries_allowed=False)
    # Exclusive creation is the cross-process gate; a failed spawn remains claimed.
    with (output / CLAIM).open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    return record


def invoke_run(output, plan, context, config):
    def read_adapter(path, seal):
        require(path == output and seal == plan['config_sha256'], 'Run config identity changed')
        context.check_config(config, output)
        return config

    def verify_adapter(path, actual_config):
        require(path == output and actual_config == config, 'Run verification config changed')
        return generic.verify(output, plan['config_sha256'])

    bindings = dict(context.namespace(), read_config=read_adapter, verify_artifacts=verify_adapter)
    generic.private(frozen.run, **bindings)(output, plan['config_sha256'])


def run_reviewed(output, launch_seal, claimed=False):
    plan, context, config = reviewed_entry(output, launch_seal)
    if claimed:
        claim = json.loads((output / CLAIM).read_bytes())
        require(claim['mode'] == 'background' and claim['output'] == str(output)
                and claim['launch_plan_sha256'] == launch_seal, 'Background claim mismatch')
        # Only the PID recorded by the parent may consume its background claim.
        launch = json.loads((output / 'population-background.json').read_bytes())
        require(launch['runner_pid'] == os.getpid(), 'Claim consumer PID differs')
    else:
        claim_once(output, launch_seal, 'foreground')
    invoke_run(output, plan, context, config)


def background(output, launch_seal):
    plan, _, _ = reviewed_entry(output, launch_seal)
    claim_once(output, launch_seal, 'background')
    # A pipe avoids the worker racing the parent PID record; no repeated EDA load.
    command = [sys.executable, '-B', str(SCRIPT), '_background-worker', '--output', str(output),
               '--launch-seal', launch_seal]
    with (output / 'population-runner.log').open('x') as stream:
        child = subprocess.Popen(command, cwd=output, stdin=subprocess.PIPE, stdout=stream,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        record = dict(runner_pid=child.pid, cwd=str(output), command=command,
                      dve_command=plan['command'], launch_plan_sha256=launch_seal,
                      actual_dve_pid_confirmed=False, automatic_retry=False)
        frozen.write(output / 'population-background.json', record)
        child.stdin.write(b'SEALED_PARENT_RECORD_READY\n')
        child.stdin.close()
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare-launch-entry', 'check-launch-entry',
                        'launch-background-reviewed', 'run-reviewed', 'verify', '_background-worker'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config-seal')
    parser.add_argument('--launch-seal')
    args = parser.parse_args(argv)
    output = output_path(args.output)
    if args.mode == 'prepare-launch-entry':
        require(args.config_seal and not args.launch_seal, 'Only explicit config seal accepted')
        result = prepare_entry(output, args.config_seal)
        print(json.dumps(dict(status='PREPARED_LAUNCH_ENTRY_NO_DVE', population=result['population'],
                              launch_plan_sha256=frozen.sha(output / PLAN))))
        return
    require(args.launch_seal and not args.config_seal, 'Explicit parent-reviewed launch seal required')
    if args.mode == '_background-worker':
        require(sys.stdin.readline() == 'SEALED_PARENT_RECORD_READY\n', 'Missing parent handshake')
        run_reviewed(output, args.launch_seal, claimed=True)
    elif args.mode == 'run-reviewed':
        run_reviewed(output, args.launch_seal)
    elif args.mode == 'launch-background-reviewed':
        print(json.dumps(background(output, args.launch_seal)))
    else:
        plan, _, _ = reviewed_entry(output, args.launch_seal)
        result = (generic.verify(output, plan['config_sha256']) if args.mode == 'verify' else
                  dict(status='LAUNCH_CONTRACT_VERIFIED_NO_DVE', population=plan['population']))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
