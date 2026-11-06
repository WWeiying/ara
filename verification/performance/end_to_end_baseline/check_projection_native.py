"""Check full SDK-stage timings, independent golden hashes and actual RTL work."""
import re

from audit import require


SCOPE = 'MATRIX_NATIVE_SCOPE model=qwen3_1p7b layer=0 source=attn_norm-0 m=4 n=128 k=2048 parts=3 trials=2 full_ggml=0'


def checksum(data):
    value = 2166136261
    for byte in data: value = ((value ^ byte)*16777619) & 0xffffffff
    return value


def fields(line, prefix):
    words = line.removeprefix(prefix).strip().split()
    require(words and all(re.fullmatch(r'[a-z_]+=[0-9]+', w) for w in words), 'Malformed numeric fields')
    pairs = [w.split('=') for w in words]
    require(len({k for k, _ in pairs}) == len(pairs), 'Duplicate numeric field')
    return {k:int(v) for k, v in pairs}


def check(text, wide, golden):
    require(wide in (0, 1) and len(golden) == 3 and all(len(b) == 2048 for b in golden), 'Checker input')
    require(not re.search(r'Fatal:|Error:|MATRIX_NATIVE_FAIL|^UVM_(?:ERROR|FATAL)\s+@', text, re.M), 'Simulator failure')
    require(text.splitlines().count(SCOPE) == 1 and text.splitlines().count(
        'MATRIX_NATIVE_RESULT trials=2 commands=24 outputs=3072 errors=0') == 1, 'Scope/terminal')
    parts = [fields(s, 'MATRIX_NATIVE_PART') for s in text.splitlines() if s.startswith('MATRIX_NATIVE_PART ')]
    trials = [fields(s, 'MATRIX_NATIVE_TRIAL') for s in text.splitlines() if s.startswith('MATRIX_NATIVE_TRIAL ')]
    perf = [fields(s, '[QBS_PERF]') for s in text.splitlines() if s.startswith('[QBS_PERF] ')]
    require(len(parts) == 6 and len(trials) == 2 and len(perf) == 24, 'Incomplete/extra work')
    require([(p['trial'], p['part']) for p in parts] == [(t, p) for t in range(2) for p in range(3)], 'Part order')
    for p in parts:
        require(p['profile'] == (1, 1, 2)[p['part']] and p['errors'] == 0 and
                p['fcsr'] == 9 and p['vcsr'] == 5 and p['admission'] > 0 and p['execution'] > 0 and
                p['checksum'] == checksum(golden[p['part']]), 'Part numerical/state check')
    for i, trial in enumerate(trials):
        subset = parts[3*i:3*i+3]
        require(trial['id'] == i and trial['commands'] == 12 and trial['errors'] == 0 and
                trial['preparation'] > 0 and trial['admission'] == sum(p['admission'] for p in subset) and
                trial['execution'] == sum(p['execution'] for p in subset) and
                trial['region'] >= trial['preparation']+trial['admission']+trial['execution'], 'Timing conservation')
    for i, p in enumerate(perf):
        expected = dict(seq=i+1, m=4, n=32, vlen=1024, lanes=4, success=1, fault=0,
                        validation_fault=0, read_fault=0, useful_pairs=262144,
                        dot_active_cycles=(4096 if wide else 8192), activation_access=0)
        require(all(p.get(k) == v for k,v in expected.items()), 'Wrong hardware work/configuration')
        require(p['busy_cycles'] > 0, 'No busy interval')
    return dict(trials=trials, parts=parts, qbs_commands=24, useful_pairs=sum(p['useful_pairs'] for p in perf),
        qbs_busy_cycles=sum(p['busy_cycles'] for p in perf), dot_issue_count=sum(p['dot_active_cycles'] for p in perf),
        preparation_cycles=sum(t['preparation'] for t in trials),
        execution_cycles=sum(t['execution'] for t in trials), region_cycles=sum(t['region'] for t in trials),
        whole_model=False, full_ggml=False, preparation_included=True)
