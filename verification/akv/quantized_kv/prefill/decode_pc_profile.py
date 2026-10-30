"""Retirement-gap localization, not causal/exclusive pipeline stall attribution."""
from bisect import bisect_right
from collections import defaultdict
import csv
import math
import re
import struct


def check_output(text,golden,q4):
    lines=text.splitlines()
    scope=f'DECODE_PROFILE_SCOPE query=19 heads=2 dim=128 visible=20 token_major=1 q4={q4}'
    if lines.count(scope)!=1 or lines.count('DECODE_PROFILE_PASS')!=1 or len(golden)!=163840:
        raise ValueError('Profile scope/completion/golden')
    reports=[x for x in lines if x.startswith('DECODE_PROFILE_RESULT ')]
    if len(reports)!=1:raise ValueError('Nonunique result')
    m=re.fullmatch(r'DECODE_PROFILE_RESULT cycles=(\d+) commands=(\d+) groups=(\d+) values=(\d+) panels=(\d+) key_bytes=(\d+) fcsr=(\d+) vcsr=(\d+) errors=(\d+) hex=([0-9a-f]{2048})',reports[0])
    if not m:raise ValueError('Malformed result')
    cycles,commands,groups,values,panels,key_bytes,fc,vc,errors=map(int,m.groups()[:9])
    if not cycles or fc>31 or (commands,groups,values,panels,key_bytes,vc,errors)!=(1,1,20,1,20*(72 if q4 else 136),5,0):
        raise ValueError('Activity/flags/errors')
    gold=struct.unpack('<40960f',golden);maximum=0.
    for i in range(256):
        word=int(m[10][i*8:(i+1)*8],16);value=struct.unpack('<f',struct.pack('<I',word))[0]
        expected=gold[(19*16+i//128)*128+i%128];error=abs(value-expected)
        if not math.isfinite(value) or not math.isfinite(expected) or error>2e-5+2e-5*abs(expected):
            raise ValueError('Golden mismatch')
        maximum=max(maximum,error)
    return dict(cycles=cycles,fcsr=fc,vcsr=vc,max_abs=maximum,outputs=256,commands=1)


def profile(trace,symbol_text,expected_cycles):
    symbols={};functions=[]
    for line in symbol_text.splitlines():
        fields=line.split()
        if len(fields)==3:
            address,kind,name=fields;symbols[name]=int(address,16)
        elif len(fields)==4:
            address,size,kind,name=fields;address=int(address,16);size=int(size,16)
            symbols[name]=address
            if kind in ('t','T') and size:functions.append((address,address+size,name))
    begin=symbols['decode_profile_begin'];end=symbols['decode_profile_end']
    functions.sort();starts=[f[0] for f in functions]
    active=False;complete=False;previous=None;last_order=-1;begin_clock=None;begin_cycle=None
    by_pc=defaultdict(lambda:dict(instructions=0,gap_cycles=0,max_gap=0))
    by_function=defaultdict(lambda:dict(instructions=0,gap_cycles=0,max_gap=0))
    for row in csv.DictReader(trace):
        if row['event']!='retire':continue
        pc=int(row['pc'],16);cycle=int(row['cycle']);order=int(row['order']);insn=int(row['insn'],16)
        if pc==begin:
            if active or complete:raise ValueError('Repeated ROI begin')
            if insn & 0xfffff07f != 0xc0002073 or int(row['rd'])==0 or int(row['trap']):raise ValueError('Begin is not rdcycle')
            active=True;previous=begin_cycle=cycle;begin_clock=int(row['rd_wdata'],16);last_order=order
            continue
        if pc==end and not active:raise ValueError('End outside ROI')
        if not active:continue
        if order<=last_order or cycle<previous or int(row['trap']):raise ValueError('ROI order/cycle/trap')
        gap=cycle-previous;previous=cycle;last_order=order
        index=bisect_right(starts,pc)-1
        name=functions[index][2] if index>=0 and pc<functions[index][1] else '<unmapped>'
        for counter in (by_pc[(pc,insn,name)],by_function[name]):
            counter['instructions']+=1;counter['gap_cycles']+=gap;counter['max_gap']=max(counter['max_gap'],gap)
        if pc==end:
            if insn & 0xfffff07f != 0xc0002073 or int(row['rd'])==0:raise ValueError('End is not rdcycle')
            if int(row['rd_wdata'],16)-begin_clock!=expected_cycles:raise ValueError('Architectural cycle mismatch')
            active=False;complete=True;retire_span=cycle-begin_cycle
    if active or not complete:raise ValueError('Incomplete ROI')
    if '<unmapped>' in by_function:raise ValueError('Unmapped ROI PC')
    if sum(v['gap_cycles'] for v in by_function.values())!=retire_span:raise ValueError('Gap accounting')
    ranked_functions=[dict(function=k,**v) for k,v in by_function.items()]
    ranked_functions.sort(key=lambda v:v['gap_cycles'],reverse=True)
    ranked_pcs=[dict(pc=f'{pc:016x}',insn=f'{insn:08x}',function=name,**v) for (pc,insn,name),v in by_pc.items()]
    ranked_pcs.sort(key=lambda v:v['gap_cycles'],reverse=True)
    return dict(architectural_cycles=expected_cycles,retirement_span_cycles=retire_span,
      retirement_minus_rdcycle=retire_span-expected_cycles,functions=ranked_functions,top_pcs=ranked_pcs[:64],
      retired_instructions=sum(v['instructions'] for v in by_function.values()),
      attribution='Gap before each retirement assigned to that retiring PC; localization only, not causal stalls')
