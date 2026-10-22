#!/usr/bin/env python3
"""One launch-bound, single-test read-only native FSM discovery; never exclusions."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_ptw_pmp0_native4 as static

OUT, HERE = static.OUT, static.HERE
SEALED = OUT / 'ptw-pmp0-native4-plan-20261006-01'
SEAL = '2318df83e951035678aa0697acbffece8a56b2b94ca77387d3a8c3b4ffbb1cb1'
SCRIPT = Path(__file__).resolve()
HOOK = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_discover_ptw_pmp0_fsm.py'
require, sha, write = static.require, static.digest, static.sample.write
tool, lifecycle = static.sample.tool, static.sample.lifecycle


def load_plan(pins):
    manifest = json.loads(static.read_bound(SEALED / 'manifest.json', pins, SEAL))
    require(set(manifest) == {str(SEALED / n) for n in ('capture-plan.json', 'inputs.txt')}, 'Wrong plan members')
    for path, expected in manifest.items():
        static.read_bound(path, pins, expected)
    plan = json.loads((SEALED / 'capture-plan.json').read_bytes())
    require(plan['status'] == 'PTW_PMP0_EXACT4_PLAN_HOLD_NATIVE_IDENTITY_NO_DVE' and
            (plan['targets'], plan['protected'], plan['selected_test_count']) == (4, 31, 1) and
            plan['capture_ready'] is False and plan['exclusions_applied'] is False,
            'Not sealed single-test static plan')
    for path, expected in plan['pins'].items():
        static.read_bound(path, pins, expected)
    require((SEALED / 'inputs.txt').read_text().splitlines() ==
            [plan['design_vdb'], plan['selected_test_vdb']], 'Wrong historical inputs')
    return plan


def check(config, output):
    pins = {}
    plan = load_plan(pins)
    require(config['schema'] == 'ptw-pmp0-readonly-native-discovery-v1' and config['output'] == str(output) and
            config['plan'] == plan and config['plan_manifest_sha256'] == SEAL and
            config['command'] == tool.launch_command(plan['tool_identity'], HOOK) and
            config['exclusions_allowed'] is False and config['native_qualified'] is False and
            config['application_approval'] is False, 'Wrong read-only discovery contract')
    require(all(config['pins'].get(p) == h for p, h in pins.items()), 'Omitted sealed evidence pin')
    lifecycle.check_inputs(config)


def read_config(output, seal):
    require(re.fullmatch('[0-9a-f]{64}', seal or '') and sha(output / 'config.json') == seal,
            'External discovery config seal differs')
    config = json.loads((output / 'config.json').read_bytes())
    check(config, output)
    return config


def prepare(output):
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh output required')
    pins = {}
    plan = load_plan(pins)
    for path in (SCRIPT, HOOK, TEST, Path(tool.__file__), Path(lifecycle.__file__)):
        static.read_bound(path, pins)
    output.mkdir()
    selection = ''.join('set pmp4_%s %s\n' % (name, lifecycle.literal(value)) for name, value in
                        (('design', plan['design_vdb']), ('test_vdb', plan['selected_test_vdb']),
                         ('test', plan['selected_test']), ('scope', plan['scope'])))
    (output / 'selection.tcl').write_text(selection)
    static.read_bound(output / 'selection.tcl', pins)
    config = dict(schema='ptw-pmp0-readonly-native-discovery-v1', output=str(output), plan=plan,
                  plan_manifest_sha256=SEAL, pins=pins, command=tool.launch_command(plan['tool_identity'], HOOK),
                  exclusions_allowed=False, native_qualified=False, application_approval=False)
    check(config, output)
    write(output / 'config.json', config)
    write(output / 'status.json', dict(status='PREPARED_NO_DVE', config_sha256=sha(output / 'config.json'),
                                      no_exclusions=True, native_qualified=False))
    print('PTW_FSM_READONLY_PREPARED ' + sha(output / 'config.json'), flush=True)


def verify(output, config):
    names = ('native-api.txt', 'native-observations.tsv', 'selected_tests.txt', 'load-gate.txt',
             'discovery-done', 'live-identity.json', 'execution.json', 'integrity-before.json',
             'integrity-after.json', 'DVEfiles/dve_gui.log', 'launcher.log')
    for name in names:
        path = output / name
        require(path.is_file() and not path.is_symlink(), 'Missing discovery evidence: ' + name)
    require(not list(output.glob('*.el')), 'Unexpected EL artifact')
    require((output / 'selected_tests.txt').read_text().splitlines() == [config['plan']['selected_test']],
            'Wrong single selected test')
    log = (output / 'DVEfiles/dve_gui.log').read_text()
    require('PTW_FSM_READONLY_DISCOVERY_DONE' in log and 'PTW_FSM_READONLY_DISCOVERY_FAILED' not in log,
            'Discovery did not complete; retain actual GUI errors')
    live = json.loads((output / 'live-identity.json').read_bytes())
    execution = json.loads((output / 'execution.json').read_bytes())
    require(execution['returncode'] == 0 and execution['launch_count'] == 1 and
            live['launch_pid'] == execution['launch_pid'] and
            live['launch_starttime'] == execution['launch_starttime'] and
            live['actual_executable'] == config['plan']['tool_identity']['executable'] and
            live['sha256'] == config['plan']['tool_identity']['identities']['executable']['sha256'],
            'Actual executable/launch identity differs')
    for name, field in (('integrity-before.json', 'checked'), ('integrity-after.json', 'unchanged')):
        record = json.loads((output / name).read_bytes())
        require(record[field] is True and record['pins'] == config['pins'], 'Integrity evidence differs')
    return dict(status='PTW_FSM_READONLY_OBSERVATIONS_NOT_NATIVE_QUALIFICATION', no_exclusions=True,
                native_qualified=False, application_approval=False, selected_tests=1,
                pid=live['pid'], files={str(output / n): sha(output / n) for n in names})


def discover(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE' and
            not any((output / n).exists() for n in ('DVEfiles', 'execution.json', 'live-ready')), 'No repeat launch')
    status = dict(status='RUNNING', config_sha256=seal, no_exclusions=True, native_qualified=False)
    write(output / 'status.json', status)
    write(output / 'integrity-before.json', dict(checked=True, pins=config['pins']))
    process = None
    try:
        env = tool.controlled_environment(config['plan']['tool_identity'], os.environ)
        env.pop('DVE', None)
        env['DVE_COVERAGE_OUTPUT'] = str(output)
        with (output / 'launcher.log').open('w') as stream:
            process = subprocess.Popen(config['command'], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            starttime = tool.process_info(process.pid)['starttime']
            execution = dict(launch_pid=process.pid, launch_starttime=starttime, launch_count=1)
            write(output / 'execution.json', execution)
            deadline, live = time.monotonic() + 60, None
            while process.poll() is None and time.monotonic() < deadline:
                live = lifecycle.find_live(process, config['plan']['tool_identity'], starttime)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, 'No launch-bound actual live DVE executable')
            write(output / 'live-identity.json', live)
            check(config, output)
            (output / 'live-ready').write_text('ACTUAL_DVE_EXECUTABLE_VERIFIED\n')
            print('PTW_FSM_READONLY_LIVE pid=%s launch_pid=%s' % (live['pid'], process.pid), flush=True)
            execution['returncode'] = process.wait(timeout=300)
            write(output / 'execution.json', execution)
        require(execution['returncode'] == 0, 'DVE exit nonzero')
        check(config, output)
        write(output / 'integrity-after.json', dict(unchanged=True, pins=config['pins']))
        status.update(verify(output, config))
        write(output / 'discovery-result.json', status)
    except Exception as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        status.update(status='FAILED', reason='%s: %s' % (type(error).__name__, error))
        raise
    finally:
        write(output / 'status.json', status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'discover', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and output.resolve() == output, 'Unsafe output')
    if args.command == 'prepare':
        prepare(output)
    elif args.command == 'discover':
        discover(output, args.seal)
    else:
        print(json.dumps(verify(output, read_config(output, args.seal)), indent=2))


if __name__ == '__main__':
    main()
