#!/usr/bin/env python3
"""Accepted offload counts in UART windows, not timed-ROI IPC or AXI bytes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def analyze(lines, trace_limit):
    active, trials, count, last_cycle = None, [], 0, -1
    for line in lines:
        if line.startswith('REGISTER_PV_BEGIN '):
            match = re.fullmatch(r'REGISTER_PV_BEGIN trial=(\d+) candidate=([01])', line.strip())
            if (not match or active is not None or len(trials)>=4 or
                int(match[1])!=len(trials) or int(match[2])!=(0,1,1,0)[len(trials)]):
                raise ValueError('Invalid ABBA window')
            active = Counter()
        elif line.startswith('REGISTER_PV_RESULT '):
            fields = dict(re.findall(r'(\w+)=(\w+)', line))
            if (active is None or not active or int(fields['trial'])!=len(trials) or
                int(fields['candidate'])!=(0,1,1,0)[len(trials)] or int(fields['errors'])):
                raise ValueError('Unmatched or failed trial')
            trials.append(dict(active)); active = None
        elif line.startswith('[ARA_CONTRACT_TRACE]'):
            count += 1
            cycle = int(re.search(r'cycle=(\d+)', line)[1])
            if cycle<=last_cycle or 'errors=0000000' not in line:
                raise ValueError('Duplicate/out-of-order trace or protocol error')
            last_cycle = cycle
            match = re.search(r'req=1/1 fire=1 id=\d+ insn=([0-9a-fA-F]+)', line)
            if active is None or not match:
                continue
            word = int(match[1],16); op = word & 127
            category = {7:'load',39:'store',87:'arithmetic'}.get(op,'other_offload')
            if op==87 and (word>>12)&7==7:
                category='vset'
            active[category]+=1
    if active is not None or len(trials)!=4 or count>=trace_limit:
        raise ValueError('Incomplete/capped trace')
    if trials[0]!=trials[3] or trials[1]!=trials[2]:
        raise ValueError('Repeated instruction mix differs')
    return dict(scope='UART BEGIN/RESULT windows include setup and checking; not cycle ROI',
        scalar_instructions_available=False, memory_bytes_measured=False,
        trace_records=count, trace_limit=trace_limit, baseline=trials[0], candidate=trials[1],
        reduction={k:trials[0].get(k,0)-trials[1].get(k,0) for k in sorted(set(trials[0])|set(trials[1]))})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--trace-limit',type=int,required=True)
    args=parser.parse_args()
    receipt=json.loads((args.run/'result.json').read_text())
    if receipt.get('state')!='PASS' or receipt.get('independent_protocol_checked') is not True:
        raise ValueError('Accepted protocol receipt required')
    command=json.loads((args.run/'work/console.command.json').read_text())['argv']
    limits=[arg for arg in command if arg.startswith('+ARA_CONTRACT_TRACE_LIMIT=')]
    if limits!=['+ARA_CONTRACT_TRACE_LIMIT='+str(args.trace_limit)]:
        raise ValueError('Trace limit does not match actual simulator invocation')
    with (args.run/'work/run.vcs.log').open() as source:
        print(json.dumps(analyze(source,args.trace_limit),indent=2))
