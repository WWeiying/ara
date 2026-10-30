#!/usr/bin/env python3
"""Exact-input residency replay; not quantizer execution or a performance estimate."""
import argparse
from collections import OrderedDict
import hashlib
import json
from pathlib import Path

ORDER=('attn_q','attn_v','attn_k','attn_output','ffn_gate','ffn_up','ffn_down')


def replay(operations,slots,budget=1024*1024,max_entry=128*1024,policy='lru'):
    if slots<1 or budget<1 or max_entry<1 or policy not in ('lru','prefix'):
        raise ValueError('Invalid capacity/policy')
    entries=OrderedDict();retained=0
    totals=dict(hits=0,misses=0,uncached=0,evictions=0,tail_rows=0,peak_payload_bytes=0)
    rows=[]
    for name,k,m,data in operations:
        if k<1 or m<1 or k%256 or len(data)!=k*m*4:raise ValueError('Invalid capture geometry')
        row=dict(operation=name,k=k,m=m,groups=m//4,tail_rows=m%4,hits=0,misses=0,uncached=0)
        totals['tail_rows']+=m%4
        size=k*16+(k//256)*4*292
        for group in range(m//4):
            raw=data[group*k*16:(group+1)*k*16]
            # Bytes are part of the dictionary key: hash collisions cannot produce hits.
            identity=(k,raw)
            if size>budget or size>max_entry or (policy=='prefix' and group>=slots):
                row['uncached']+=1;continue
            if identity in entries:
                row['hits']+=1;entries.move_to_end(identity);continue
            row['misses']+=1
            while len(entries)>=slots or retained+size>budget:
                _,removed=entries.popitem(last=False);retained-=removed;totals['evictions']+=1
            entries[identity]=size;retained+=size
            totals['peak_payload_bytes']=max(totals['peak_payload_bytes'],retained)
        for key in ('hits','misses','uncached'):totals[key]+=row[key]
        rows.append(row)
    return dict(policy=policy,slots=slots,budget=budget,max_entry=max_entry,operations=rows,totals=totals)


def load(root):
    operations=[];pins={}
    for name in ORDER:
        folder=root/('blk_0_'+name+'_weight')
        meta=folder/'activation_f32.json';binary=folder/'activation_f32.bin';op=folder/'operator.json'
        for path in (meta,binary,op):pins[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
        shape=json.loads(meta.read_text());kind=json.loads(op.read_text());k,m,b2,b3=shape['shape']
        if shape['type']!='f32' or (b2,b3)!=(1,1) or shape['strides']!=[4,k*4,k*m*4,k*m*4] or \
                kind['op']!='GGML_OP_MUL_MAT' or kind['activation_quantization']!='Q8_K' or kind['phase']!='prefill':
            raise ValueError('Unsupported capture: '+name)
        data=binary.read_bytes()
        if len(data)!=shape['nbytes']:raise ValueError('Capture length')
        operations.append((name,k,m,data))
    return operations,pins


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--captures',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh report required')
    ops,pins=load(a.captures)
    report=dict(scope='Captured layer-0 ordered preparation residency only; not actual runtime dispatch, numerical validation or hardware timing',
                order=list(ORDER),input_pins=pins,
                policies=[replay(ops,n,policy=policy) for policy in ('lru','prefix') for n in (1,2,3,4,8)])
    _,after=load(a.captures)
    if pins!=after:raise ValueError('Capture drift')
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({r['policy']+':'+str(r['slots']):r['totals'] for r in report['policies']},indent=2))


if __name__=='__main__':main()
