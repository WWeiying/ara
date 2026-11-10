#!/usr/bin/env python3
"""Fixed internal-FDT build variant; reuse immutable prepare03 and toolenv02."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V4_SHA = '993de91dc79e3fa0ec9dac839dc20117a4bdc6a5874cd47b22737aa86c85661f'
OWN = ('build_v5.py', 'test_build_v5.py', 'BUILD_V5.md',
       'build_v4.py', 'test_build_v4.py', 'BUILD_V4.md')


def predecessor():
    import hashlib
    path = HERE / 'build_v4.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != V4_SHA:
        raise ValueError('Sealed V4 validator drift')
    spec = importlib.util.spec_from_file_location('fdt_frozen_build_v4', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v4 = predecessor()
sha, require = v4.sha, v4.require
PREPARED, PREPARE_SHA, OUT = v4.PREPARED, v4.PREPARE_SHA, v4.OUT
TOOLENV = OUT / 'stage5_qemu_toolenv_20261110_02'
TOOLENV_SHA = 'ffc26812e9e4de51bea4b9ef8c47411f88a5f8a5407580855c0f927d8aaf378d'


def identity():
    pins = {name: sha(HERE / name) for name in OWN}
    return pins, v4.hashlib.sha256(v4.base().canonical(pins)).hexdigest()


def configure_argv(prepared):
    return [*v4.configure_argv(prepared), '--enable-fdt=internal']


def checked_dependencies():
    prepared = v4.checked_prepared()
    old = v4.checked_toolenv(TOOLENV, TOOLENV_SHA)
    require(old['configure_argv'] == v4.configure_argv(prepared), 'Inherited configure contract drift')
    return prepared


def checked_commands(report, path, prepared):
    require(report['environment'] == v4.environment(path), 'Build environment drift')
    commands = report['commands']
    require(len(commands) == 2, 'Missing/extra build commands')
    for row, argv, seconds, name in zip(commands,
            (configure_argv(prepared), [v4.NINJA, '-j4', 'qemu-system-riscv64']),
            (900, 1800), ('configure.log', 'build.log')):
        require(row['argv'] == argv and row['cwd'] == str(path) and row['timeout'] == seconds and
                row['state'] == 'EXITED' and type(row['returncode']) is int and row['returncode'] == 0 and
                row['pid'] > 0 and row['started_ns'] < row['ended_ns'] and
                row['log_sha256'] == sha(path / name), 'Build execution receipt mismatch')
    require(commands[0]['ended_ns'] <= commands[1]['started_ns'], 'Overlapping build steps')
    owner = report['service_owner']
    require(re.fullmatch(r'stage5-qemu-build-[A-Za-z0-9_-]+\.service', owner['unit']) and
            owner['main_pid'] > 0 and re.fullmatch('[0-9a-f]{32}', owner['invocation_id']) and
            '/' + owner['unit'] in owner['cgroup'], 'Build service ownership receipt invalid')


def checked_build(build_dir, reviewed_build_sha256):
    """Read-only shared admission API. V4/failed/other-option receipts cannot pass."""
    r = v4.base()
    path = Path(build_dir).resolve(strict=True)
    require(sha(path / 'build.json') == reviewed_build_sha256, 'Unreviewed build receipt')
    report = r.read(path / 'build.json')
    require(report['schema'] == 'stage5-qemu-build-v5' and report['state'] == 'BUILT_NOT_EXECUTED' and
            report['prepare_sha256'] == PREPARE_SHA and report['prepared'] == str(PREPARED) and
            report['preflight'] == str(TOOLENV) and report['preflight_sha256'] == TOOLENV_SHA and
            report['predecessor_validator_sha256'] == V4_SHA and report['fdt_selection'] == 'internal' and
            report['guest_executed'] is False and report['post_pins_match'] is True and
            report['source_review_sha256'] == identity()[1] and report['required_execution_gates'] == r.GATES,
            'Build not admitted')
    prepared = checked_dependencies()
    checked_commands(report, path, prepared)
    require(report['executable'] == str(path / 'qemu-system-riscv64') and
            sha(report['executable']) == report['executable_sha256'], 'Runtime binary drift')
    return report


def build(args):
    r = v4.base()
    require(identity()[1] == args.reviewed_inputs_sha256, 'Unreviewed successor inputs')
    owner = r.service_owner(args.service)
    prepared = checked_dependencies()
    output = r.fresh(args.output, 'stage5_qemu_build_')
    report = dict(schema='stage5-qemu-build-v5', state='FAIL', commands=[], service_owner=owner,
                  prepare_sha256=PREPARE_SHA, prepared=str(PREPARED), preflight=str(TOOLENV),
                  preflight_sha256=TOOLENV_SHA, source_review_sha256=args.reviewed_inputs_sha256,
                  predecessor_validator_sha256=V4_SHA, fdt_selection='internal',
                  guest_executed=False, required_execution_gates=r.GATES)
    try:
        (output / 'home').mkdir()
        (output / 'tmp').mkdir()
        env = v4.environment(output)
        report['environment'] = env
        r.bounded(configure_argv(prepared), output, 900, output / 'configure.log', report['commands'], env)
        r.bounded([v4.NINJA, '-j4', 'qemu-system-riscv64'], output, 1800,
                  output / 'build.log', report['commands'], env)
        checked_dependencies()
        require(identity()[1] == args.reviewed_inputs_sha256, 'Successor inputs changed')
        require(r.service_owner(args.service) == owner, 'Build service ownership changed')
        checked_commands(report, output, prepared)
        report.update(state='BUILT_NOT_EXECUTED', executable=str(output / 'qemu-system-riscv64'),
                      executable_sha256=sha(output / 'qemu-system-riscv64'), post_pins_match=True)
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        r.write_new(output / 'build.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('identity')
    run = sub.add_parser('build')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--service', required=True)
    run.add_argument('--reviewed-inputs-sha256', required=True)
    args = p.parse_args()
    print(json.dumps(identity() if args.command == 'identity' else build(args), indent=2))


if __name__ == '__main__':
    main()
