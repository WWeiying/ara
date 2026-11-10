#!/usr/bin/env python3
"""Strict software-call/output/command accounting, separate from SoC admission."""
import json
from pathlib import Path
import re
import struct

PHASES = tuple('phase_' + name + '_cycles' for name in
               ('setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
                'scheduler', 'commit', 'fault', 'terminal'))
TIMES = ('quant', 'pack', 'plan', 'execute', 'drain')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(line, prefix, strings=()):
    require(line.startswith(prefix), 'Wrong prefix')
    result = {}
    for token in line[len(prefix):].split():
        require(token.count('=') == 1, 'Malformed field')
        name, value = token.split('=')
        require(name and value and name not in result, 'Duplicate/empty field')
        if name in strings:
            result[name] = value
        else:
            require(re.fullmatch('[0-9]+', value) is not None, 'Not an unsigned decimal')
            result[name] = int(value)
    return result


def check(text, build, expected, expected_flags, enabled):
    n = build['n']
    modes = build['trials']
    trial_count = len(modes)
    require(build['m'] == 8 and build['k'] == 2048 and len(expected) == 8*n*4 and
            modes in ([4, 8, 8, 4], [4, 4], [8, 8]), 'Wrong build/expected scope')
    seeds = build.get('flag_seeds', [1, 1, 1, 1] if trial_count == 4 else None)
    require(seeds == ([0, 8] if trial_count == 2 else [1, 1, 1, 1]), 'Wrong exception seeds')
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate firmware success')
    require(not re.search(r'(?im)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|'
                          r'STAGE2_PROJECTION_FAIL|\bTIMEOUT\b|\bTIMED OUT\b)', text), 'Simulation failure')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*', line) is not None,
                    'UVM failure')
    perf, trials, values = [], [], {}
    meta = footer = None
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            require(meta is None, 'Command after result reporting')
            p = fields(line, '[QBS_PERF] ')
            require(p['seq'] == len(perf)+1 and p['success'] == 1 and p['fault'] == 0 and
                    p['validation_fault'] == p['read_fault'] == p['validation_error'] == 0,
                    'Command sequence/terminal failure')
            require(sum(p[k] for k in PHASES) == p['busy_cycles'] > 0 and
                    p['phase_fault_cycles'] == 0, 'Engine phase partition mismatch')
            perf.append(p)
        elif line.startswith('STAGE2_PROJECTION_META '):
            require(meta is None and footer is None, 'Duplicate metadata')
            meta = fields(line, 'STAGE2_PROJECTION_META ', ('id',))
            require(meta == dict(id=build['build_id'], m=8, k=2048, n=n, trials=trial_count, whole_model=0),
                    'Build metadata mismatch')
        elif line.startswith('STAGE2_PROJECTION_TRIAL '):
            r = fields(line, 'STAGE2_PROJECTION_TRIAL ')
            require(meta is not None and footer is None and r['id'] == len(trials) and len(trials) < trial_count,
                    'Trial order/identity')
            mode = build['trials'][r['id']]
            require(set(r) == {'id', 'mode', 'status', 'commands', 'context', *TIMES, 'total',
                               'flags', 'expected_flags', 'q8_bad', 'output_bad', 'guards_bad'},
                    'Trial schema mismatch')
            require(r['mode'] == mode and r['status'] == r['context'] == r['q8_bad'] ==
                    r['output_bad'] == r['guards_bad'] == 0 and r['commands'] == n//16,
                    'Work/admission/numerical failure')
            seed = seeds[r['id']]
            require(r['flags'] == r['expected_flags'] == expected_flags | seed,
                    'Sticky exceptions mismatch')
            require(all(r[k] > 0 for k in TIMES) and sum(r[k] for k in TIMES) == r['total'],
                    'Software cycle partition mismatch')
            trials.append(r)
        elif line.startswith('STAGE2_PROJECTION_OUTPUT '):
            m = re.fullmatch(r'STAGE2_PROJECTION_OUTPUT trial=([0-9]+) row=([0-9]+) '
                             r'col=([0-9]+) bits=([0-9a-f]{8})', line)
            require(m is not None and footer is None, 'Output record malformed/late')
            trial, row, col = map(int, m.groups()[:3])
            key = (trial, row, col)
            require(trial == len(trials)-1 and 0 <= row < 8 and 0 <= col < n and key not in values,
                    'Output missing, duplicate or outside shape')
            value = int(m[4], 16)
            require(value == struct.unpack_from('<I', expected, 4*(row*n+col))[0],
                    'Independent bit-exact output mismatch')
            values[key] = value
        elif line.startswith('STAGE2_PROJECTION_PASS '):
            require(meta is not None and footer is None and len(trials) == trial_count, 'Early/duplicate footer')
            footer = fields(line, 'STAGE2_PROJECTION_PASS ')
            require(footer == {'errors': 0}, 'Failed firmware footer')
        elif line.startswith('STAGE2_PROJECTION_'):
            raise ValueError('Unknown workload record')
    require(meta is not None and footer is not None and len(trials) == trial_count and
            len(values) == trial_count*8*n and len(perf) == trial_count*(n//16), 'Incomplete evidence')
    count = n//16
    for trial, t in enumerate(trials):
        commands = perf[trial*count:(trial+1)*count]
        mode = t['mode']
        tn = 16 if mode == 8 else 32
        expected_dot = 8192 // (2 if enabled and mode == 8 else 1)
        for p in commands:
            require((p['m'], p['n'], p['vlen'], p['lanes']) == (mode, tn, 1024, 4),
                    'Command M/N/VLEN/lane mismatch')
            require(p['weight_bytes'] == tn*8*144 and p['activation_bytes'] == mode*8*292 and
                    p['useful_pairs'] == mode*tn*2048 and p['dot_active_cycles'] == expected_dot and
                    p['pair_capacity'] == p['useful_pairs'] and p['tiles'] == 64,
                    'Command work/capacity mismatch')
            require(p['activation_access'] == p['context_fill_count'] == p['context_reuse_count'] ==
                    p['context_validation_fault_count'] == 0, 'Unplanned context reuse')
        t['native_busy'] = sum(p['busy_cycles'] for p in commands)
        require(t['native_busy'] <= t['execute'], 'Engine cycles exceed execute ROI')
        t['software_execute_remainder'] = t['execute']-t['native_busy']
    return dict(state='PASS', trials=trials, outputs_bit_exact=trial_count*8*n,
                command_count=len(perf), numerical='Host independently checks every reported output; '
                'firmware compares complete Q8 bytes and guards against independent constants',
                scope='Real full-K projection slice, complete software invocation; not full layer/model',
                whole_model=False, full_output_width=build['full_output_width'])


def check_run(log, directory, enabled):
    build = json.loads((directory / 'build.json').read_text())
    return check(log.read_text(), build, (directory / 'data/expected.bin').read_bytes(),
                 struct.unpack('<I', (directory / 'data/flags.bin').read_bytes())[0], enabled)
