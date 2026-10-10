#!/usr/bin/env python3
"""Seal actual failed-attempt observations and focused successor tests; no EDA."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'out'
SIX = OUT / 'branch-combo-six-policy-707-20261006-01'
PTW = OUT / 'ptw-pmp0-fsm-native-discovery-20261006-01'
SIX_SHA = '478debd6ca1601c96d1126fd9031124f5add18b5cfea8fff41e379f4c07825b0'
PTW_SHA = '88f20a8d1c0e93c16b0f97dcd25469d0bd8ce88fac254adcc7c2eda75f8e5870'


def require(value, message):
    if not value:
        raise ValueError(message)


def collect():
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'Missing/aliased evidence')
        raw = path.read_bytes()
        value = hashlib.sha256(raw).hexdigest()
        require(expected is None or expected == value, 'Fixed external seal differs')
        require(str(path) not in pins or pins[str(path)] == value, 'Conflicting input pin')
        pins[str(path)] = value
        return raw
    cfg = json.loads(read(SIX / 'config.json', SIX_SHA))
    status = json.loads(read(SIX / 'status.json'))
    require(status['status'] == 'FAILED' and status['reason'] == 'ValueError: Missing/aliased six-policy evidence',
            'Original six failure differs')
    log = read(SIX / 'DVEfiles/dve_gui.log').decode()
    require('QBSAPP_LOAD_GATE_PASSED' in log and 'FF1_AUDIT before 1728' in log and
            'SIX_COMBO_ERROR gui_list_select: List item(s) given by ""' in log and
            'EXP1272_AUDIT before' not in log and 'PACK208_AUDIT before' not in log,
            'Actual six failure stage differs')
    require(read(SIX / 'final-empty.el') == b'', 'Six cleanup final EL not empty')
    for name in ('execution.json', 'live-identity.json', 'integrity-after.json', 'initial-empty.el'):
        read(SIX / name)
    with (SIX / 'exponent/states_before.tsv').open(newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    read(SIX / 'exponent/states_before.tsv')
    require(rows and len({r['scope'] for r in rows}) == 1 and all(r['excluded'] == '0' for r in rows),
            'Not one complete first-scope raw audit')
    scope = rows[0]['scope']
    expected = cfg['groups']['exponent']['plan']['scopes'][scope]['branch']
    require(len(rows) == len(expected) == 220 and
            [r['coordinate'] for r in rows] == [r['point']['native_id'] + ',' + r['point']['vector'] for r in expected],
            'Completed first-scope identities differ')
    missing = [name for name in ('applied.el', 'after-root.el', 'summary_raw.csv', 'summary_applied.csv',
                                'summary_reset.csv') if not (SIX / name).exists()]
    require(len(missing) == 5, 'Unexpected six application/report evidence')
    pc = json.loads(read(PTW / 'config.json', PTW_SHA))
    ps = json.loads(read(PTW / 'status.json'))
    require(ps['status'] == 'FAILED' and ps['reason'] == "KeyError: 'actual_executable'", 'PTW driver failure differs')
    live = json.loads(read(PTW / 'live-identity.json'))
    execution = json.loads(read(PTW / 'execution.json'))
    require(set(live) == {'pid', 'executable', 'executable_verified', 'starttime', 'launch_pid', 'launch_starttime'} and
            live['executable_verified'] is True and live['executable'] == pc['plan']['tool_identity']['executable'] and
            execution['returncode'] == 0 and execution['launch_count'] == 1 and
            live['launch_pid'] == execution['launch_pid'] and live['launch_starttime'] == execution['launch_starttime'],
            'Actual launch-bound tool identity differs')
    for name, field in (('integrity-before.json', 'checked'), ('integrity-after.json', 'unchanged')):
        value = json.loads(read(PTW / name))
        require(value[field] is True and value['pins'] == pc['pins'], 'Actual discovery integrity differs')
    require(read(PTW / 'selected_tests.txt').decode().splitlines() == [pc['plan']['selected_test']], 'Wrong selected sample')
    observations = read(PTW / 'native-observations.tsv').decode()
    require('RESULT\t0\t{ptw_stage_q state_q}' in observations and
            'SELECT_STATE_Q\t{gui_list_select -id CovDetail.1 -list fsmnames -select {state_q}}\nRESULT\t0' in observations and
            'RESULT\t0\t{{ state_q }}' in observations and 'RESULT\t0\t200229904' in observations,
            'Actual FSM name/handle observations differ')
    native_log = read(PTW / 'DVEfiles/dve_gui.log').decode()
    require('PTW_FSM_READONLY_DISCOVERY_DONE' in native_log and
            'PTW_FSM_READONLY_DISCOVERY_FAILED' not in native_log and
            "Required argument '-item' was not found." in native_log and
            '[-fsmShow string]' in native_log, 'Actual API evidence differs')
    for name in ('native-api.txt', 'load-gate.txt', 'discovery-done', 'launcher.log'):
        read(PTW / name)
    require(not list(PTW.glob('*.el')), 'Unexpected discovery EL')
    for path, expected_sha in pc['pins'].items():
        read(path, expected_sha)
    for path in (HERE / 'six_policy_singleton_selection_v2.tcl',
                 HERE / 'test_six_policy_singleton_selection_v2.py', Path(__file__).resolve()):
        read(path)
    test = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_six_policy_singleton_selection_v2'],
                          cwd=HERE, text=True, capture_output=True, timeout=60)
    require(test.returncode == 0 and 'Ran 6 tests' in test.stderr and test.stderr.rstrip().endswith('OK'),
            'Focused actual Tcl successor tests did not pass')
    return dict(status='SEALED_FAILURE_DIAGNOSTICS_NOT_APPLICATION_OR_NATIVE_APPROVAL',
                six=dict(original_status='FAILED', original_config_sha256=SIX_SHA,
                         completed_first_exponent_scope=scope, completed_points=220, missing=missing,
                         pack_started=False, runtime_getter_raw_value_recorded=False,
                         source_supported_hypothesis='Blank/nested-empty old selection passed to unselect at scope transition.',
                         focused_frozen_helper_reproduction=True, successor_tests=6,
                         successor_full_driver_integrated=False, successor_DVE_run=False,
                         remaining_test='Minimal actual cross-scope query with getter argument logging before any full retry.'),
                ptw=dict(original_status='FAILED', config_sha256=PTW_SHA, pid=live['pid'],
                         executable=live['executable'], actual_GUI_discovery_completed=True,
                         fsm_name_tokens=['ptw_stage_q', 'state_q'], detail_handle='200229904',
                         state_arc_row_tokens_observed=False, no_EL=True, native_qualified=False,
                         driver_error='Verifier assumed actual_executable/sha256 keys instead of sealed tool helper return schema.',
                         query_error='META calls lacked required -item; value API is signal/time-oriented. Not proof that FSM introspection is unsupported.'),
                tests=dict(returncode=test.returncode, stdout=test.stdout, stderr=test.stderr), pins=pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh output required')
    result = collect()
    output.mkdir()
    (output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    value = hashlib.sha256((output / 'evidence.json').read_bytes()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps({str(output / 'evidence.json'): value}, indent=2) + '\n')
    print(result['status'] + ' manifest_sha256=' + hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest())
