"""Independent output/activity checks for the bounded native Prefill ABBA."""
import math
import re
import struct


def check_log(text, golden, q4):
    cap = f'PREFILL_CAP q4={q4} rows=8 d=128 first_query=16 tokens=20 trials=4'
    lines = text.splitlines()
    if lines.count(cap) != 1 or lines.count('PREFILL_SUITE_PASS') != 1:
        raise ValueError('Missing unique capability/completion')
    if len(golden) != 163840:
        raise ValueError('Golden shape')
    gold = struct.unpack('<40960f', golden)
    rows = []
    pending = None
    for line in lines:
        if line.startswith('PREFILL_BEGIN '):
            if pending is not None: raise ValueError('Nested trial')
            pending = line
        if not line.startswith('PREFILL_RESULT '): continue
        match = re.fullmatch(r'PREFILL_RESULT trial=(\d+) shared=(\d+) cycles=(\d+) commands=(\d+) values=(\d+) fcsr=(\d+) vcsr=(\d+) errors=(\d+) hex=([0-9a-f]{8192})', line)
        if not match: raise ValueError('Malformed trial')
        trial, shared, cycles, commands, values, fc, vc, errors = map(int, match.groups()[:8])
        if trial != len(rows) or trial >= 4 or shared != (0,1,1,0)[trial]:
            raise ValueError('Trial order')
        if pending != f'PREFILL_BEGIN trial={trial} shared={shared}': raise ValueError('Trial scope')
        pending = None
        if not cycles or commands != 4 or values != (20 if shared else 74) or fc > 31 or vc != 5 or errors:
            raise ValueError('Activity/status mismatch')
        words = tuple(int(match[9][i:i+8],16) for i in range(0,8192,8))
        if rows and (words != rows[0]['words'] or fc != rows[0]['fcsr']):
            raise ValueError('Paired bits or flags differ')
        maximum = 0.
        for row in range(8):
            for d in range(128):
                value = struct.unpack('<f', struct.pack('<I', words[row*128+d]))[0]
                expected = gold[((16+row//2)*16+row%2)*128+d]
                error = abs(value-expected)
                if not math.isfinite(value) or not math.isfinite(expected) or error > 2e-5+2e-5*abs(expected):
                    raise ValueError(f'Golden mismatch row={row} d={d}')
                maximum = max(maximum,error)
        rows.append(dict(cycles=cycles,shared=shared,fcsr=fc,words=words,max_abs=maximum))
    if pending is not None or len(rows)!=4: raise ValueError('Incomplete trials')
    baseline = (rows[0]['cycles']+rows[3]['cycles'])/2
    shared = (rows[1]['cycles']+rows[2]['cycles'])/2
    return dict(baseline_cycles=baseline,shared_cycles=shared,speedup=baseline/shared,
                trials=[{k:v for k,v in row.items() if k!='words'} for row in rows],
                outputs_per_trial=1024,commands_per_trial=4,paired_bitexact=True,
                scope='QBS per-query GQA baseline versus cross-query V sharing; not RVV or whole model')
