#!/usr/bin/env python3
"""Audit actual-model preparation/reuse activity, never QEMU performance."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def fields(line):
    return dict(re.findall(r'(\w+)=([^\s]+)',line))


def analyze(text):
    modes={}; mode=None
    for line in text.splitlines():
        if line.startswith('Q8K_MODEL_BEGIN '):
            mode=int(fields(line)['enabled'])
            if mode in modes: raise ValueError('Duplicate model mode')
            modes[mode]=dict(records={},groups=Counter(),bytes=Counter(),gaps=Counter(),skips=0,ended=False,summary=None)
        elif line.startswith('Q8K_MODEL_END '):
            if mode is None or int(fields(line)['enabled'])!=mode: raise ValueError('Model end mismatch')
            modes[mode]['ended']=True
        elif line.startswith('GGML_RISCV_QBS_CROSS_OP '):
            if mode is None: raise ValueError('Trace outside model')
            modes[mode]['skips']+=int(fields(line)['quantization_skipped'])
        elif line.startswith('GGML_RISCV_QBS_LIFETIME '):
            if mode is None: raise ValueError('Trace outside model')
            state=modes[mode]; row=fields(line); seq=int(row['seq'])
            if seq!=len(state['records'])+1: raise ValueError('Missing or duplicate sequence')
            reuse=int(row['reusable']); match=int(row['match_seq'])
            if reuse not in (0,1) or bool(match)!=bool(reuse): raise ValueError('Invalid match')
            if reuse:
                old=state['records'].get(match)
                keys=('graph_epoch','source_id','activation_type','m','k','bytes','digest')
                if old is None or any(old[key]!=row[key] for key in keys) or row['same_tensor']!='1':
                    raise ValueError('Reuse identity mismatch')
                state['gaps'][seq-match]+=1
            state['records'][seq]=row
            key=(int(row['m']),int(row['k']),reuse)
            state['groups'][key]+=1; state['bytes'][key]+=int(row['bytes'])
        elif line.startswith('GGML_RISCV_QBS_LIFETIME_SUMMARY '):
            if mode is None or modes[mode]['summary'] is not None: raise ValueError('Unexpected summary')
            modes[mode]['summary']=fields(line)
    if set(modes)!={0,1}: raise ValueError('Need complete OFF/ON model')
    result={}
    for mode,state in modes.items():
        summary=state['summary']
        if not state['ended'] or summary is None: raise ValueError('Incomplete mode')
        totals=dict(quantizations=len(state['records']),
                    exact_reuse_candidates=sum(n for (m,k,r),n in state['groups'].items() if r),
                    quantized_bytes=sum(state['bytes'].values()),
                    reusable_quantized_bytes=sum(n for (m,k,r),n in state['bytes'].items() if r),
                    cross_op_quantization_skips=state['skips'])
        if any(int(summary[key])!=value for key,value in totals.items()):
            raise ValueError('Summary does not reconcile')
        result[str(mode)]=dict(totals=totals,
            groups=[dict(m=m,k=k,already_quantized_exact_duplicate=bool(r),calls=n,
                         quantized_bytes=state['bytes'][(m,k,r)]) for (m,k,r),n in sorted(state['groups'].items())],
            duplicate_sequence_gaps=dict(sorted(state['gaps'].items())))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    args=parser.parse_args()
    raw=args.log.read_bytes()
    print(json.dumps(dict(log=str(args.log.resolve()),sha256=hashlib.sha256(raw).hexdigest(),
        scope='Observed preparation calls and exact-byte duplicate candidates; not safe-cache eligibility or RTL time',
        modes=analyze(raw.decode())),indent=2))


if __name__=='__main__': main()
