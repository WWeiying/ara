"""Strict complete-payload firmware verdict, all-output and QBS work checker."""
import argparse
import json
from pathlib import Path
import re
import struct

PHASES = tuple('phase_'+name+'_cycles' for name in ('setup', 'activation', 'weight', 'compute',
    'overlap', 'drain', 'scheduler', 'commit', 'fault', 'terminal'))
MODES, SEEDS = (4, 8, 8, 4), (0, 8, 0, 8)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(line, prefix, strings=()):
    require(line.startswith(prefix), 'Wrong record prefix')
    result = {}
    for token in line[len(prefix):].split():
        require(token.count('=') == 1, 'Malformed field')
        key, value = token.split('=')
        require(key not in result and key and value, 'Duplicate/empty field')
        require(key in strings or re.fullmatch('[0-9]+', value), 'Nondecimal field')
        result[key] = value if key in strings else int(value)
    return result


def check(text, build, expected, loans=True):
    require(build['trials'] == list(MODES) and build['flag_seeds'] == list(SEEDS) and
        (build['m'], build['k'], build['n'], build['commands'], build['outputs_per_trial']) == (8, 2048, 32, 8, 256)
        and build['activation_payload_bytes'] == 18688 and build['q8_equal_before_oracle'] is True and
        build['cache'] is False and build['context_replay'] is False and len(expected) == 256*4, 'Wrong pair scope')
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate firmware completion')
    require(not re.search(r'(?im)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|EXTENSION_M8_FAIL|'
        r'EXTENSION_M8_ABORT|\bTIMEOUT\b|\bTIMED OUT\b)', text), 'Simulation failure')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*', line), 'UVM error/fatal')
    meta = footer = None
    trials, perf, values, beats, totals = [], [], {}, [], []
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            require(meta is None, 'Late command')
            p = fields(line, '[QBS_PERF] ')
            require(p['seq'] == len(perf)+1 and p['success'] == 1 and
                p['fault'] == p['validation_fault'] == p['read_fault'] == p['validation_error'] == 0, 'Command failure/order')
            require(sum(p[k] for k in PHASES) == p['busy_cycles'] > 0 and p['phase_fault_cycles'] == 0, 'Phase accounting')
            perf.append(p)
        elif line.startswith('STAGE2_SOC_LOAN '):
            beats.append(fields(line, 'STAGE2_SOC_LOAN '))
        elif line.startswith('STAGE2_SOC_LOAN_DONE '):
            totals.append(fields(line, 'STAGE2_SOC_LOAN_DONE '))
        elif line.startswith('EXTENSION_M8_META '):
            require(meta is None and footer is None, 'Duplicate metadata')
            meta = fields(line, 'EXTENSION_M8_META ', ('id',))
            require(meta == dict(id=build['build_id'], m=8, k=2048, n=32, trials=4, whole_model=0, cache=0), 'Metadata identity')
        elif line.startswith('EXTENSION_M8_TRIAL '):
            r = fields(line, 'EXTENSION_M8_TRIAL ')
            require(meta is not None and footer is None and r['id'] == len(trials) < 4, 'Trial ordering')
            index = len(trials)
            require(set(r) == {'id', 'mode', 'status', 'commands', 'coop', 'prep', 'plan', 'execute', 'drain',
                'total', 'flags', 'prep_flags', 'vcsr', 'payload_bad', 'output_bad', 'guard_bad'}, 'Trial schema')
            require(r['mode'] == MODES[index] and r['commands'] == 2 and r['coop'] == 1 and
                r['status'] == r['payload_bad'] == r['output_bad'] == r['guard_bad'] == 0 and r['vcsr'] == 5, 'SDK/payload/guard/layout failure')
            require(r['flags'] == build['engine_flags'] | build['prep_flags'] | SEEDS[index] and
                r['prep_flags'] == build['prep_flags'] | SEEDS[index], 'Exact/sticky FFLAGS mismatch')
            require(all(r[k] > 0 for k in ('prep', 'plan', 'execute', 'drain')) and
                sum(r[k] for k in ('prep', 'plan', 'execute', 'drain')) == r['total'], 'Complete call ROI accounting')
            trials.append(r)
        elif line.startswith('EXTENSION_M8_OUTPUT '):
            match = re.fullmatch(r'EXTENSION_M8_OUTPUT trial=([0-9]+) row=([0-9]+) col=([0-9]+) bits=([0-9a-f]{8})', line)
            require(match is not None and footer is None, 'Malformed/late output')
            trial, row, col = map(int, match.groups()[:3])
            key = (trial, row, col)
            require(trial == len(trials)-1 and 0 <= row < 8 and 0 <= col < 32 and key not in values, 'Missing/duplicate/out-of-scope output')
            value = int(match[4], 16)
            require(value == struct.unpack_from('<I', expected, 4*(row*32+col))[0], 'Independent bit-exact output mismatch')
            values[key] = value
        elif line.startswith('EXTENSION_M8_PASS '):
            require(meta is not None and footer is None and len(trials) == 4, 'Early/duplicate footer')
            footer = fields(line, 'EXTENSION_M8_PASS ')
            require(footer == {'errors': 0}, 'Failed footer')
        elif line.startswith('EXTENSION_M8_'):
            raise ValueError('Unknown pair record')
    require(meta is not None and footer is not None and len(perf) == 8 and len(values) == 4*256, 'Incomplete pair evidence')
    for trial, r in enumerate(trials):
        mode, tn = MODES[trial], 16 if MODES[trial] == 8 else 32
        commands = perf[trial*2:trial*2+2]
        for p in commands:
            require((p['m'], p['n'], p['vlen'], p['lanes']) == (mode, tn, 1024, 4), 'Command layout/geometry')
            require(p['weight_bytes'] == tn*8*144 and p['activation_bytes'] == mode*8*292 and
                p['useful_pairs'] == mode*tn*2048 and p['pair_capacity'] == p['useful_pairs'] and
                p['dot_active_cycles'] == (4096 if mode == 8 else 8192) and p['tiles'] == 64, 'Work/capacity mismatch')
            require(p['activation_access'] == p['context_fill_count'] == p['context_reuse_count'] == p['context_validation_fault_count'] == 0,
                'Unexpected context reuse')
        r['native_busy'] = sum(p['busy_cycles'] for p in commands)
        require(r['native_busy'] <= r['execute'], 'Engine cycles exceed SDK execute ROI')
    if loans:
        require(len(beats) == 4*8 and len(totals) == 4 and {r['lane'] for r in totals} == set(range(4)), 'Missing lane accounting')
        for lane in range(4):
            rows = [r for r in beats if r['lane'] == lane]
            require([r['seq'] for r in rows] == list(range(1, 9)), 'Lane sequence mismatch')
            total = 0
            for i, row in enumerate(rows):
                count = 4096 if MODES[i//2] == 8 else 0
                total += count
                require(row == dict(lane=lane, seq=i+1, accepted=count, core_issued=count,
                    core_completed=count, returned=count), 'Loan work mismatch')
            require([r for r in totals if r['lane'] == lane] == [dict(lane=lane, commands=8, accepted=total, returned=total)], 'Lane terminal mismatch')
    return dict(state='PASS', trials=trials, outputs_bit_exact=1024, command_count=8,
        full_payload_checked_bytes=4*18688, whole_model=False, cache=False,
        numerical='Exact C-ref output bits and FFLAGS on identical actual GNU producers; no tolerance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--software', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.log.read_text(), json.loads((args.software/'build.json').read_text()),
        (args.software/'data/expected.bin').read_bytes()), sort_keys=True))
