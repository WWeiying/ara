"""Check complete real-capture outputs and activities independently of ELF PASS."""
import math
import re
import struct


def check_log(text, golden, q4):
    lines=text.splitlines()
    required=[f'VCACHE_CAP q4={q4} rows=16 d=128 first_query=0 tokens=8 trials=4',
        'VCACHE_SCOPE whole_call=1 admission=1 scatter=1 baseline=grouped_qbs',
        'VCACHE_LAYOUT token_major=1 physical_kv_heads=8 selected_head=0','VCACHE_SUITE_PASS']
    if any(lines.count(line)!=1 for line in required):raise ValueError('Scope/capability/completion')
    if len(golden)!=163840:raise ValueError('Golden extent')
    gold=struct.unpack('<40960f',golden);row_bytes=72 if q4 else 136
    if [l for l in lines if l.startswith('VCACHE_PANEL')]!=[
        f'VCACHE_PANEL trial={i} panels=2 key_bytes={12*row_bytes}' for i in range(4)]:
        raise ValueError('Panel counts')
    rows=[];pending=None
    for line in lines:
        if line.startswith('VCACHE_BEGIN '):
            if pending is not None:raise ValueError('Nested trial')
            pending=line
        if not line.startswith('VCACHE_RESULT '):continue
        m=re.fullmatch(r'VCACHE_RESULT trial=(\d+) shared=(\d+) cycles=(\d+) commands=(\d+) values=(\d+) fcsr=(\d+) vcsr=(\d+) errors=(\d+) hex=([0-9a-f]{16384})',line)
        if not m:raise ValueError('Malformed result')
        trial,shared,cycles,commands,values,fc,vc,errors=map(int,m.groups()[:8])
        if trial!=len(rows) or trial>=4 or shared!=(0,1,1,0)[trial]:raise ValueError('Trial order')
        if pending!=f'VCACHE_BEGIN trial={trial} shared={shared}':raise ValueError('Unscoped result')
        pending=None
        if not cycles or commands!=8 or values!=(8 if shared else 12) or fc>31 or not fc&8 or vc!=5 or errors:
            raise ValueError('Activity/status/flags')
        words=tuple(int(m[9][i:i+8],16) for i in range(0,16384,8))
        if rows and (words!=rows[0]['words'] or fc!=rows[0]['fcsr']):raise ValueError('Paired mismatch')
        maximum=0.
        for row in range(16):
            for d in range(128):
                actual=struct.unpack('<f',struct.pack('<I',words[row*128+d]))[0]
                expected=gold[((row//2)*16+row%2)*128+d];error=abs(actual-expected)
                if not math.isfinite(actual) or not math.isfinite(expected) or error>2e-5+2e-5*abs(expected):
                    raise ValueError(f'Golden mismatch row={row} d={d}')
                maximum=max(maximum,error)
        rows.append(dict(cycles=cycles,shared=shared,fcsr=fc,words=words,max_abs=maximum))
    if pending is not None or len(rows)!=4:raise ValueError('Incomplete trial')
    baseline=(rows[0]['cycles']+rows[3]['cycles'])/2
    candidate=(rows[1]['cycles']+rows[2]['cycles'])/2
    return dict(baseline_cycles=baseline,candidate_cycles=candidate,speedup=baseline/candidate,
        trials=[{k:v for k,v in row.items() if k!='words'} for row in rows],
        outputs_per_trial=2048,commands_per_trial=8,paired_bitexact=True,
        scope='Whole-call two-group Prefill V cache; not whole model')
