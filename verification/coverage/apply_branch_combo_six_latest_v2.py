#!/usr/bin/env python3
"""Fresh707 successor: frozen six-policy core plus strict empty-selection adapter."""
import argparse
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import apply_branch_combo_six_latest as core
import capture_operand_1144 as lifecycle

OUT, HERE = core.OUT, core.HERE
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_apply_branch_combo_six_latest_v2.py'
HELPER = HERE / 'six_policy_singleton_selection_v2.tcl'
HELPER_TEST = HERE / 'test_six_policy_singleton_selection_v2.py'
ATTEMPT = OUT / 'branch-combo-six-policy-707-20261006-01'
ATTEMPT_SHA = '478debd6ca1601c96d1126fd9031124f5add18b5cfea8fff41e379f4c07825b0'
SCHEMA = 'six-policy707-empty-selection-successor-v2'
require, sha, write, pin = core.require, core.sha, core.write, core.pin
METADATA = {'core_config_path', 'core_config_sha256', 'previous_attempt', 'previous_config_sha256', 'selection_adapter'}


def additional_files(output):
    return [SCRIPT, TCL, TEST, HELPER, HELPER_TEST, output / 'frozen-core-config.json',
            *[ATTEMPT / n for n in ('config.json', 'status.json', 'DVEfiles/dve_gui.log',
                                   'exponent/states_before.tsv', 'final-empty.el')]]


def inherited_view(config, frozen):
    return {key: value for key, value in config.items()
            if key not in METADATA and key not in ('schema', 'command', 'pins')}


def check_config(config, output):
    require(config['schema'] == SCHEMA and config['core_config_path'] == str(output / 'frozen-core-config.json') and
            config['previous_attempt'] == str(ATTEMPT) and config['previous_config_sha256'] == ATTEMPT_SHA and
            config['selection_adapter'] == str(HELPER), 'Wrong successor contract')
    frozen = core.load_sealed(output / 'frozen-core-config.json', config['core_config_sha256'])
    core.check_config(frozen, output)
    require(set(config) == set(frozen) | METADATA and
            inherited_view(config, frozen) == inherited_view(frozen, frozen) and config['population'] == 707,
            'Successor changed inherited all-point/base/protection contract')
    require(config['command'] == lifecycle.tool.launch_command(config['plan']['tool_identity'], TCL),
            'Wrong actual successor command')
    expected = dict(frozen['pins'])
    for path in additional_files(output):
        pin(expected, path, config['pins'].get(str(path)))
    require(config['pins'] == expected and config['pins'][str(ATTEMPT / 'config.json')] == ATTEMPT_SHA,
            'Unexpected or conflicting successor source/evidence pins')
    original_status = json.loads((ATTEMPT / 'status.json').read_bytes())
    require(original_status['status'] == 'FAILED' and original_status['config_sha256'] == ATTEMPT_SHA and
            (ATTEMPT / 'final-empty.el').read_bytes() == b'', 'Original failure not preserved')
    lifecycle.check_inputs(config)


def read_config(output, seal):
    config = core.load_sealed(output / 'config.json', seal)
    check_config(config, output)
    return config


def prepare(output):
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh output required')
    original = core.read_config(ATTEMPT, ATTEMPT_SHA)
    require(original['population'] == 707, 'Not explicit707 original base')
    core.prepare(output, original['admitted_base'], original['raw_report'],
                 original['raw_verification_sha256'], original['evidence_sha256'])
    raw = (output / 'config.json').read_bytes()
    (output / 'frozen-core-config.json').write_bytes(raw)
    frozen = json.loads(raw)
    config = copy.deepcopy(frozen)
    config.update(schema=SCHEMA, command=lifecycle.tool.launch_command(frozen['plan']['tool_identity'], TCL),
                  core_config_path=str(output / 'frozen-core-config.json'),
                  core_config_sha256=sha(output / 'frozen-core-config.json'),
                  previous_attempt=str(ATTEMPT), previous_config_sha256=ATTEMPT_SHA, selection_adapter=str(HELPER))
    for path in additional_files(output):
        pin(config['pins'], path)
    check_config(config, output)
    write(output / 'config.json', config)
    write(output / 'status.json', dict(status='PREPARED_NO_DVE', config_sha256=sha(output / 'config.json'),
                                      tests=707, targets=core.TOTAL, protected=core.PROTECTED,
                                      aggregate_admission=False, previous_attempt_preserved=True))
    print('SIX707_SUCCESSOR_PREPARED ' + sha(output / 'config.json'), flush=True)


def verify_artifacts(output, config):
    require((output / 'DVEfiles/dve_gui.log').read_text().splitlines().count('SIX2_SELECTION_ADAPTER_INSTALLED') == 1,
            'Selection adapter not actually installed')
    # Frozen verifier checks all native signatures, 19370 points at every stage,
    # raw/reset707 reports, tool identity, exact actual command and expanded pins.
    return core.verify_artifacts(output, config)


def run(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE' and
            not any((output / n).exists() for n in ('live-ready', 'execution.json', 'DVEfiles')), 'No repeat launch')
    identity = config['plan']['tool_identity']
    status = dict(status='RUNNING', config_sha256=seal, aggregate_admission=False, application_approval=False)
    write(output / 'status.json', status)
    write(output / 'integrity-before.json', dict(checked=True, pins=config['pins'], membership=config['plan']['input_membership']))
    process = None
    try:
        env = lifecycle.environment(identity, output)
        for key in ('DVE_REVIEWED_WAIVERS', 'DEBUG_CAPTURE_SEAL', 'OP1144_BASE_HOOK', 'OBD_SELECTION', 'FF1_CAPTURE_SEAL', 'EXP1272_CAPTURE_SEAL'):
            env.pop(key, None)
        with (output / 'launcher.log').open('w') as stream:
            process = subprocess.Popen(config['command'], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = lifecycle.tool.process_info(process.pid)['starttime']
            execution = dict(launch_pid=process.pid, launch_starttime=start, launch_count=1,
                             timeout_seconds=core.TIMEOUT, command=config['command'])
            write(output / 'execution.json', execution)
            deadline, live = time.monotonic() + 60, None
            while process.poll() is None and time.monotonic() < deadline:
                live = lifecycle.find_live(process, identity, start)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, 'No launch-bound actual DVE executable')
            write(output / 'live-identity.json', live)
            lifecycle.check_inputs(config)
            (output / 'live-ready').write_text('LIVE_EXECUTABLE_VERIFIED\n')
            print('SIX707_V2_DVE_STARTED pid=%s launch_pid=%s' % (live['pid'], process.pid), flush=True)
            execution['returncode'] = process.wait(timeout=core.TIMEOUT)
            write(output / 'execution.json', execution)
        require(execution['returncode'] == 0, 'DVE exited nonzero')
        lifecycle.check_inputs(config)
        write(output / 'integrity-after.json', dict(unchanged=True, pins=config['pins'], membership=config['plan']['input_membership']))
        status.update(verify_artifacts(output, config))
        status['files'][str(output / 'config.json')] = sha(output / 'config.json')
        write(output / 'capture-result.json', status)
        status['capture_result_sha256'] = sha(output / 'capture-result.json')
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and output.resolve() == output, 'Unsafe output')
    if args.command == 'prepare':
        prepare(output)
    elif args.command == 'run':
        run(output, args.seal)
    else:
        print(json.dumps(verify_artifacts(output, read_config(output, args.seal)), indent=2))
