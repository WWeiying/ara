"""Explicit full-QKV successor of the checked, immutable prefix workload."""
import math
import re

from audit import require
from check_projection_native import checksum, fields

N = (2048, 1024, 1024)
K = 2048
M = 4
SCOPE = ('MATRIX_FULL_SCOPE model=qwen3_1p7b layer=0 source=attn_norm-0 '
         'm=4 nq=2048 nk=1024 nv=1024 k=2048 parts=3 trials=1 full_ggml=0')


def once(text, old, new):
    require(text.count(old) == 1, 'Full-shape template anchor differs: '+old)
    return text.replace(old, new, 1)


def native_source(text):
    text = once(text, 'K=2048, N=128, M=4', 'K=2048, N=2048, M=4')
    text = once(text, 'const size_t bytes[] = {128*8*144, 128*8*144, 128*8*210};',
                'const unsigned n[] = {2048,1024,1024};\n    const size_t bytes[] = {2048*8*144,1024*8*144,1024*8*210};')
    text = once(text,
        'MATRIX_NATIVE_SCOPE model=qwen3_1p7b layer=0 source=attn_norm-0 m=4 n=128 k=2048 parts=3 trials=2 full_ggml=0', SCOPE)
    text = once(text, 'trial < 2', 'trial < 1')
    text = once(text, 'M, N, K};', 'M, n[part], K};')
    text = once(text, 'output[part]+16, M*N, N,', 'output[part]+16, M*n[part], n[part],')
    require(text.count('M*N*sizeof(float)') == 2, 'Numerical/checksum extent anchors')
    text = text.replace('M*N*sizeof(float)', 'M*n[part]*sizeof(float)')
    text = once(text, 'i < M*N;', 'i < M*n[part];')
    text = once(text,
        'for (unsigned i = 0; i < 64; ++i) errors += raw[i] != 0xa5 || raw[64+M*N*4+i] != 0xa5;',
        'for (unsigned i = 0; i < 64; ++i) errors += raw[i] != 0xa5;\n'
        '            for (size_t i = 64+M*n[part]*4; i < sizeof(output[part]); ++i) errors += raw[i] != 0xa5;')
    text = once(text, 'profile=%u admission=', 'profile=%u n=%u admission=')
    text = once(text, 'trial, part, profiles[part], (unsigned long)admit_part[part]',
                'trial, part, profiles[part], n[part], (unsigned long)admit_part[part]')
    text = once(text, 'commands != 12', 'commands != 128')
    text = once(text, 'trials=2 commands=24 outputs=3072', 'trials=1 commands=128 outputs=16384')
    return text.replace('MATRIX_NATIVE_', 'MATRIX_FULL_')


def golden_source(text, reference_header):
    text = once(text, '#include "../../qbs/qbs_ref.h"', '#include "'+str(reference_header)+'"')
    text = once(text, 'K = 2048, N = 128, M = 4', 'K = 2048, N = 2048, M = 4')
    text = once(text, 'for (unsigned part = 0; part < 3; ++part) {',
                'const unsigned ns[] = {2048,1024,1024};\n'
                '    for (unsigned part = 0; part < 3; ++part) {\n        const unsigned n=ns[part];')
    text = once(text, 'const size_t bytes = N*row_bytes;', 'const size_t bytes = n*row_bytes;')
    text = once(text, 'weights, bytes, N, KB,', 'weights, bytes, n, KB,')
    text = once(text, 'start < N;', 'start < n;')
    text = once(text, 'output+row*N+start', 'output+row*n+start')
    text = once(text, 'name, output, sizeof(output)', 'name, output, M*n*sizeof(float)')
    text = once(text, 'm=4 n=128 k=2048 flags=%u', 'm=4 n=%u k=2048 flags=%u')
    text = once(text, 'part, profiles[part], flags);', 'part, profiles[part], n, flags);')
    return text


def check(text, wide, golden):
    require(not re.search(r'Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@', text, re.M), 'Simulator failure')
    require(wide in (0, 1) and len(golden) == 3 and
            [len(data) for data in golden] == [M*n*4 for n in N], 'Full-shape golden geometry')
    require(text.splitlines().count(SCOPE) == 1 and text.splitlines().count(
        'MATRIX_FULL_RESULT trials=1 commands=128 outputs=16384 errors=0') == 1 and
        'MATRIX_FULL_FAIL' not in text, 'Full-shape scope/terminal')
    parts = [fields(s, 'MATRIX_FULL_PART') for s in text.splitlines() if s.startswith('MATRIX_FULL_PART ')]
    trials = [fields(s, 'MATRIX_FULL_TRIAL') for s in text.splitlines() if s.startswith('MATRIX_FULL_TRIAL ')]
    commands = [fields(s, '[QBS_PERF]') for s in text.splitlines() if s.startswith('[QBS_PERF] ')]
    require(len(parts) == 3 and len(trials) == 1 and len(commands) == 128, 'Incomplete full projection')
    for part, row in enumerate(parts):
        expected = dict(trial=0, part=part, profile=(1,1,2)[part], n=N[part], errors=0, fcsr=9, vcsr=5,
                        checksum=checksum(golden[part]))
        require(all(row.get(k) == v for k,v in expected.items()) and
                row['admission'] > 0 and row['execution'] > 0, 'Full output/numerical/state mismatch')
    trial = trials[0]
    require(trial['id'] == 0 and trial['commands'] == 128 and trial['errors'] == 0 and trial['preparation'] > 0 and
            trial['admission'] == sum(p['admission'] for p in parts) and
            trial['execution'] == sum(p['execution'] for p in parts) and
            trial['region'] >= trial['preparation']+trial['admission']+trial['execution'], 'Stage accounting')
    expected_profiles = [1]*96+[2]*32
    for i, row in enumerate(commands):
        expected = dict(seq=i+1, m=4, n=32, vlen=1024, lanes=4, success=1, fault=0,
            validation_fault=0, read_fault=0, useful_pairs=262144,
            dot_active_cycles=4096 if wide else 8192, activation_access=0,
            weight_bytes=32*8*(144 if expected_profiles[i] == 1 else 210), activation_bytes=9344)
        require(all(row.get(k) == v for k,v in expected.items()), 'Wrong full command work')
    start = 0
    for part, row in enumerate(parts):
        count = N[part]//32
        require(sum(c['busy_cycles'] for c in commands[start:start+count]) <= row['execution'], 'Busy outside SDK interval')
        start += count
    require(all(math.isfinite(x) for p in parts for x in (p['execution'], p['admission'])), 'Nonfinite timing')
    return dict(trials=trials, parts=parts, qbs_commands=128, useful_pairs=33554432,
        qbs_busy_cycles=sum(c['busy_cycles'] for c in commands),
        dot_issue_count=sum(c['dot_active_cycles'] for c in commands),
        preparation_cycles=trial['preparation'], execution_cycles=trial['execution'],
        region_cycles=trial['region'], full_n=True, whole_model=False, full_ggml=False,
        preparation_included=True, single_reset_trial=True)
