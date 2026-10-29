#!/usr/bin/env python3
"""Count repeated V decodes from audited real masks; not cycle estimates."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from build_production_native import capture_inputs, ROOT


def schedule(visible,gqa,kv_heads,cache_tokens=32):
    if not visible or gqa<1 or kv_heads<1 or cache_tokens<0 or any(n<1 for n in visible):
        raise ValueError('Invalid schedule')
    rows=[length for length in visible for _ in range(gqa)]
    groups=[]
    for first in range(0,len(rows),8):
        lengths=rows[first:first+8];maximum=max(lengths);commands=0
        for tile in range(0,maximum,32):
            active=[min(32,max(0,n-tile)) for n in lengths]
            row=0
            while row<len(active):
                if not active[row]:row+=1;continue
                end=row+1
                while end<len(active) and active[end]==active[row]:end+=1
                while row<end:
                    width=4 if end-row>=4 else 2 if end-row>=2 else 1
                    row+=width;commands+=1
        groups.append(dict(first_row=first,rows=len(lengths),visible_max=maximum,
                           commands=commands,value_decodes=maximum,pv_updates=sum(lengths)))
    old=sum(g['value_decodes'] for g in groups)*kv_heads
    cached=(min(max(visible),cache_tokens)+sum(max(0,g['visible_max']-cache_tokens) for g in groups))*kv_heads
    return dict(groups_per_kv_head=groups,kv_heads=kv_heads,commands=sum(g['commands'] for g in groups)*kv_heads,
                pv_updates=sum(rows)*kv_heads,value_decodes=old,bounded_cache_value_decodes=cached,
                eliminated_decodes=old-cached,cache_tokens=cache_tokens)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh report required')
    audit=ROOT/'verification/out/quant-prefill-capture-audit-20261028-01'
    if json.loads((audit/'result.json').read_text())['state']!='PASS':raise ValueError('Unaccepted captures')
    audited=json.loads((audit/'manifest.json').read_text());pins={};reports={}
    def pin(path):pins[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (Path(__file__),Path(__file__).with_name('build_production_native.py'),
                 audit/'result.json',audit/'manifest.json',
                 ROOT/'software/akv/experimental/quantized_kv/prefill/execute.h',
                 ROOT/'software/akv/experimental/quantized_kv/prefill/prefix_schedule.h'):pin(path)
    for kind in ('q4_0','q8_0'):
        capture=ROOT/'verification/out/quant-prefill-capture-20261028-01'/kind/'prefill/block'
        for path in capture_inputs(capture,kind,audited):pin(path)
        mask=struct.unpack('<5120H',(capture/'attn_mask_input-0.bin').read_bytes())
        visible=[]
        for row in range(20):
            values=mask[row*256:(row+1)*256];n=0
            while n<256 and values[n]==0:n+=1
            if not n or any(v!=0xfc00 for v in values[n:]):raise ValueError('Non-prefix mask')
            visible.append(n)
        reports[kind]=dict(prefixes=visible,
            accepted_slice=schedule(visible[16:20],2,1),
            next_two_group_slice=schedule(visible[:8],2,1),
            whole_captured_operator=schedule(visible,2,8),
            cache_storage_bytes_at_d128=32*128*4,
            cache_storage_max_d256=32*256*4)
        assert reports[kind]['accepted_slice']['value_decodes']==20
        assert reports[kind]['accepted_slice']['commands']==4
    for path,wanted in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=wanted:raise ValueError('Source drift')
    result=dict(state='STATIC_SCHEDULE_AUDIT',scope='software decode calls, not DRAM bytes or speedup',
                source_pins=pins,reports=reports)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
