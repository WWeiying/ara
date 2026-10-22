#!/usr/bin/env python3
"""Offline, fail-closed audit of this bounded campaign; never launches EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PREFIX = ROOT / 'verification/out'
RUNS = {
    'old_partial': 'vldu-old-02',
    'old_split': 'vldu-old-split-01',
    'new_long': 'vldu-new-03',
    'old_small': 'vldu-small-old-01',
    'new_small': 'vldu-small-new-01',
    'old_mul': 'mul-old-01',
    'new_mul': 'mul-new-01',
    'old_guard': 'guard-old-128x4-01',
    'reject_guard': 'guard-new-128x4-01',
    'new_guard': 'guard-new-256x4-01',
}
RTL = ['hardware/src/lane/simd_mul.sv', 'hardware/src/vlsu/vldu.sv', 'hardware/src/ara.sv']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit():
    records, logs = {}, {}
    for key, suffix in RUNS.items():
        directory = PREFIX / ('ara-upstream-20261009-agent-' + suffix)
        status = json.loads((directory / 'status.json').read_text())
        pins = json.loads((directory / 'pins.json').read_text())
        for path, pin in pins.items():
            require(sha(directory / path) == pin['sha256'], 'Snapshot drift: ' + str(directory / path))
        record = {'directory': str(directory), 'status': status,
                  'pins_sha256': sha(directory / 'pins.json'),
                  'command_sha256': sha(directory / 'command.json'),
                  'rtl': {path: pins[path]['sha256'] for path in RTL}}
        if key == 'reject_guard':
            log = (directory / 'compile.console.log').read_text()
            require(status['state'] == 'COMPILE_FAILED' and status['compile_exit'] != 0,
                    'Expected elaboration rejection')
            require('Error-[EEST] $error elaboration system task' in log and
                    '[ara] The vector length must hold at least one ELEN-bit word per lane.' in log and
                    '\n1 error\n' in log, 'Wrong compile failure; not guard evidence')
            record['scope'] = 'actual assertion block extracted from ara.sv, NOT full Ara elaboration'
        else:
            require(status['compile_exit'] == 0, 'Compile failed: ' + key)
            require(sha(directory / 'simv') == status['image_sha256'], 'Image drift: ' + key)
            record['runtime_objects_at_audit'] = {
                str(path.relative_to(directory)): sha(path)
                for path in sorted((directory / 'simv.daidir').rglob('*.so'))}
            log = (directory / 'run.console.log').read_text()
            if key.startswith('old_') and key in ('old_partial', 'old_split'):
                require(status['state'] == 'FAIL', 'Old defect no longer detected')
                require('Fatal:' in log and '\nDESCRIPTOR_BEFORE_LAST_R\n' in log and
                        'POP=1 RREADY=0 len_q=0 len_d=0' in log, 'Wrong old failure')
                require('VLDU_SUITE_PASS' not in log, 'Old failure cannot pass')
            else:
                require(status['state'] == 'PASS' and status['run_exit'] == 0,
                        'Expected actual PASS: ' + key)
                require(not re.search(r'(?m)^(?:Fatal|Error)(?:-|:|\[)', log), 'Diagnostics: ' + key)
        logs[key] = log
        record['log_sha256'] = hashlib.sha256(log.encode()).hexdigest()
        records[key] = record
    for key, path in [('new_long', RTL[1]), ('new_small', RTL[1]),
                      ('new_mul', RTL[0]), ('new_guard', RTL[2])]:
        require(records[key]['rtl'][path] == sha(ROOT / path), 'Candidate RTL drift: ' + path)
    full = logs['new_long']
    for marker in ['VLDU_ALL_SKIP_PASS noR=40', 'VLDU_INDEX_MASK_SKIP_PASS skips=13',
                   'VLDU_QUEUE_OWNER_PASS owners=2 peak=2',
                   'VLDU_NATURAL_PAGE_CROSS_PASS bytes=4140',
                   'VLDU_SUITE_PASS cases=18 bytes=39558 R=2624 desc=124 skips=53',
                   'POP=0 RREADY=0 len_q=0 len_d=0 rptr_q=0 rptr_d=1']:
        require(marker in full, 'Missing long-burst evidence: ' + marker)
    old_small = re.findall(r'(?m)^VLDU_.*PASS.*$', logs['old_small'])
    new_small = re.findall(r'(?m)^VLDU_.*PASS.*$', logs['new_small'])
    require(len(new_small) == 98 and old_small == new_small, 'Small-burst semantic/count regression')
    old_time = re.findall(r'(?m)^Time: (\d+) ps$', logs['old_small'])
    new_time = re.findall(r'(?m)^Time: (\d+) ps$', logs['new_small'])
    require(len(old_time) == 1 and old_time == new_time, 'Small-burst cycle regression')
    for key in ('old_mul', 'new_mul'):
        require('SIMD MUL equivalence PASS configurations=24' in logs[key], 'MUL missing terminal')
        require(len(re.findall(r'(?m)^SIMD MUL case PASS ', logs[key])) == 24, 'Missing MUL configuration')
    old_mul = sorted(re.findall(r'(?m)^SIMD MUL case PASS .*$', logs['old_mul']))
    new_mul = sorted(re.findall(r'(?m)^SIMD MUL case PASS .*$', logs['new_mul']))
    require(old_mul == new_mul, 'MUL acceptance/count/retirement regression')
    require(len(re.findall(r'(?m)^OLD_R_UNDRIVEN ', logs['old_mul'])) == 24, 'Missing old r diagnostic')
    require('OLD_R_UNDRIVEN' not in logs['new_mul'], 'Candidate suppressed default assertion')
    require('GUARD_ACCEPT lanes=4 vlen=128 stride=0' in logs['old_guard'], 'Missing original alias evidence')
    require('GUARD_ACCEPT lanes=4 vlen=256 stride=1' in logs['new_guard'], 'Missing legal guard boundary')
    return {'state': 'PASS', 'scope': 'bounded real-module VCS units; not integrated signoff',
            'guard_scope': 'extracted actual assertions, not full Ara parameter elaboration',
            'small_old_new_same_sim_time_ps': int(old_time[0]),
            'mul_checks_per_revision': sum(int(n) for n in re.findall(r'checks=(\d+)', '\n'.join(new_mul))),
            'mul_retired_per_revision': sum(int(n) for n in re.findall(r'retired=(\d+)', '\n'.join(new_mul))),
            'source_freeze': {path: sha(ROOT / path) for path in RTL}, 'runs': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit()
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    else:
        print(text, end='')
