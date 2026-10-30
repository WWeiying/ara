"""Decode pair: full output bits, golden values, activity and ordered ROI checks."""
import math
import re
import struct


def check_log(text,golden,q4,query):
    if type(query) is not int or not 0<=query<20:raise ValueError('Invalid captured query')
    mode_field='candidate'
    marker='REGISTER_PV_BINDINGS value=shared_rvv_q8_0 baseline=current_shared candidate=register_pv'
    if text.splitlines().count(marker)!=1:raise ValueError('Experiment identity')
    if mode_field not in ('aligned','candidate'):raise ValueError('Unknown comparison field')
    lines=text.splitlines()
    for expected in (
        f'REGISTER_PV_SCOPE whole_call=1 query={query} heads=2 dim=128 visible={query+1} token_major=1 trials=4',
        f'REGISTER_PV_FORMAT q4={q4}','REGISTER_PV_SUITE_PASS'):
        if lines.count(expected)!=1:raise ValueError('Missing unique scope/format/completion')
    if len(golden)!=163840 or q4 not in (0,1):raise ValueError('Capture contract')
    gold=struct.unpack('<40960f',golden);rows=[];pending=None
    for line in lines:
        if line.startswith('REGISTER_PV_BEGIN '):
            if pending is not None:raise ValueError('Nested trial')
            pending=line
        if not line.startswith('REGISTER_PV_RESULT '):continue
        pattern=r'REGISTER_PV_RESULT trial=(\d+) aligned=(\d+) cycles=(\d+) commands=(\d+) groups=(\d+) values=(\d+) panels=(\d+) key_bytes=(\d+) fcsr=(\d+) vcsr=(\d+) errors=(\d+) hex=([0-9a-f]{2048})'
        m=re.fullmatch(pattern.replace('aligned=',mode_field+'='),line)
        if not m:raise ValueError('Malformed trial')
        trial,aligned,cycles,commands,groups,values,panels,key_bytes,fc,vc,errors=map(int,m.groups()[:11])
        if trial!=len(rows) or trial>=4 or aligned!=(0,1,1,0)[trial]:raise ValueError('ABBA order')
        if pending!=f'REGISTER_PV_BEGIN trial={trial} {mode_field}={aligned}':raise ValueError('ROI pair')
        pending=None
        if not cycles or (commands,groups,values,panels,key_bytes,vc,errors)!=(1,1,query+1,1,(query+1)*(72 if q4 else 136),5,0) or fc>31:
            raise ValueError('Activity/flags/status')
        words=tuple(int(m[12][i:i+8],16) for i in range(0,2048,8))
        if rows and (words!=rows[0]['words'] or fc!=rows[0]['fcsr']):raise ValueError('Paired bits/flags')
        maximum=0.
        for i,word in enumerate(words):
            value=struct.unpack('<f',struct.pack('<I',word))[0]
            expected=gold[(query*16+i//128)*128+i%128];error=abs(value-expected)
            if not math.isfinite(value) or not math.isfinite(expected) or error>2e-5+2e-5*abs(expected):
                raise ValueError('Golden mismatch')
            maximum=max(maximum,error)
        rows.append(dict(cycles=cycles,fcsr=fc,words=words,max_abs=maximum,**{mode_field:aligned}))
    if len(rows)!=4 or pending is not None:raise ValueError('Incomplete trials')
    old=(rows[0]['cycles']+rows[3]['cycles'])/2
    new=(rows[1]['cycles']+rows[2]['cycles'])/2
    return dict(baseline_cycles=old,candidate_cycles=new,speedup=old/new,
        paired_bitexact=True,outputs_per_trial=256,commands_per_trial=1,
        trials=[{k:v for k,v in row.items() if k!='words'} for row in rows],
        query_index=query, visible_tokens=query+1,
        scope='Complete Decode call, shared RVV versus register-PV; not whole model')
