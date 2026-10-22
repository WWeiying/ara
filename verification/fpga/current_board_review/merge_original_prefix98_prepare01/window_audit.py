#!/usr/bin/env python3
"""Additional full-file helper ownership and post-HTIF parking checks; no execution."""
import json
import re
import sys
from pathlib import Path
sys.dont_write_bytecode = True
from reference_check import HERE, NAME, instructions, require
from prepare_prefix import base, save

LINE = re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')


def contract(elf):
    selected = instructions(elf,NAME+'_op_4')
    unused = {r['pc']:r for op in range(21) if op!=4
              for r in instructions(elf,NAME+'_op_'+str(op))}
    capacity = instructions(elf,NAME+'_capacity')
    exit_body = instructions(elf,'replay_exit')
    store, = [r for r in exit_body if r['text'].startswith('sd\t')]
    park, = [r for r in exit_body if r['pc']>store['pc']]
    require(park['insn']=='a001' and park['text'].startswith('j\t'), 'Original self parking loop')
    return selected,unused,capacity,store,park


def check(lines, c):
    selected,unused,capacity,store,park = c
    pcs = {r['pc']:i for i,r in enumerate(selected)}
    cap_pcs = {r['pc']:i for i,r in enumerate(capacity)}
    step=cap_step=calls=caps=retired=parking=boot=0
    exit_seen=False
    for line in lines:
        require('trap_' not in line, 'Unexpected raw trap')
        m=LINE.match(line)
        if not m:
            require(not line.strip(), 'Unparsed nonempty raw record')
            continue
        pc,code=int(m[1],16),int(m[2],16)
        if pc<0x80000000:
            require(not retired, 'Boot PC after firmware')
            boot+=1
            continue
        if exit_seen:
            require(pc==park['pc'] and code==int(park['insn'],16), 'Non-parking execution after HTIF')
            parking+=1
            continue
        retired+=1
        require(pc not in unused, 'Unused helper internal PC')
        if step:
            require(pc==selected[step]['pc'], 'Noncontiguous selected helper')
        if cap_step:
            require(pc==capacity[cap_step]['pc'], 'Noncontiguous capacity helper')
        if pc in pcs:
            i=pcs[pc]
            require(i==step and code==int(selected[i]['insn'],16), 'Selected helper order/encoding')
            if i==0:
                require(caps==1 and calls<98, 'Selected helper ownership')
                calls+=1
            step=(step+1)%len(selected)
        elif pc in cap_pcs:
            i=cap_pcs[pc]
            require(i==cap_step and code==int(capacity[i]['insn'],16), 'Capacity order/encoding')
            if i==0:
                require(caps==calls==0, 'Duplicate or late capacity')
                caps+=1
            cap_step=(cap_step+1)%len(capacity)
        else:
            require(code&127!=0x57 and not(code&127 in (0x07,0x27) and
                    (code>>12)&7 in (0,5,6,7)), 'RVV outside original helper windows')
        if pc==store['pc']:
            require(code==int(store['insn'],16) and re.search(r'\bmem\s+0x[0-9a-f]+\s+0x0*1\s*$',m[3]),
                    'Nonzero or missing HTIF store')
            require(calls==98 and caps==1 and step==cap_step==0,'Incomplete helper windows at exit')
            exit_seen=True
    require(exit_seen,'Missing HTIF exit')
    return dict(calls=calls,capacity_calls=caps,firmware_to_htif=retired,
                boot_records=boot,allowed_post_htif_parking=parking,unused_helpers_executed=0)


def main():
    proof=json.loads((HERE/'source_elf_proof.json').read_text())
    elf=Path(proof['spike_elf']['path'])
    c=contract(elf)
    trace=HERE/'reference/commits.log'
    with trace.open() as f:
        measured=check(f,c)
    prefix=[]
    with trace.open() as f:
        for line in f:
            prefix.append(line)
            m=LINE.match(line)
            if m and int(m[1],16)==c[0][-1]['pc']:
                break
    require(len(prefix)<200000,'Negative fixture size')
    unused_int=next(r for r in c[1].values() if r['text'].startswith('mv\t'))
    unused_target=next(r for r in c[1].values() if r['insn']=='30880c57')
    negatives=[]
    for label,r,reason in [('unused_integer',unused_int,'Unused helper'),
                           ('unused_gather',unused_target,'Unused helper'),
                           ('duplicate_op4_interior',c[0][6],'Selected helper order/encoding')]:
        bad=prefix+[f"core   0: 3 0x{r['pc']:016x} (0x{r['insn']})\n"]
        try:
            check(bad,c)
        except ValueError as e:
            require(reason in str(e),'Wrong negative reason: '+str(e))
            negatives.append(dict(name=label,status='REJECTED',reason=str(e)))
        else:
            raise ValueError('Bad helper window accepted')
    save(HERE/'window_audit.json',dict(status='FULL_RAW_WINDOW_AND_PARKING_PASS_NOT_DUT',
        **measured,negative_tests=negatives,trace_sha256=base.sha(trace),
        elf_sha256=base.sha(elf),checker_sha256=base.sha(Path(__file__))))
    print('FULL_RAW_WINDOW_AND_PARKING_PASS_NOT_DUT',measured)


if __name__=='__main__':
    main()
