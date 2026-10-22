#!/usr/bin/env python3
"""Offline Host adapter test, not RVFI/DUT evidence and not a new Spike run.

Project actual Spike scalar commits into the checker's row interface. Vector
memory is deliberately absent, as in scalar RVFI. Fault partial commits are
not retired. Instruction-order pseudo-cycles are not hardware cycles. The
actual reference HTIF=1 terminal is explicitly bridged to the DUT CTRL=0
endpoint only after its independent validation; no CSV is manufactured.
"""
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
import dut_check as d
import importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('indexed_load_reference',HERE/'reference.py')
receipt=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipt)


def read(path):return json.loads(Path(path).read_text())
def verify(pins):
    d.require(all(receipt.sha(p)==h for p,h in pins.items()),'Pinned reference drift')


def analyze(member):
    root=HERE/('reference_'+member+'01');ready=read(root/'READY.json')
    pins={str(root/p):h for p,h in ready['outputs'].items()}
    pins.update(ready['input_pins']);verify(pins)
    s=read(root/'spike.symbols.json');c=d.Checker(s,0)
    partial=0;htif=[];order=0
    with (root/'spike.trace').open() as f:
        for line in f:
            m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m:continue
            pc,insn,tail=int(m[2],16),int(m[3],16),m[4]
            accesses=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
            if pc==s['mt_target'] and not partial:
                d.require(accesses==[(0x40000008,None)] and 'e64 m1 l5' in tail and re.search(r'c8_vstart 0x0*2\b',tail),'Wrong partial fault contract')
                partial+=1;continue
            gprs=[(int(r),int(v,16)) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)]
            d.require(len(gprs)<=1,'Multiple scalar writes in one commit')
            r={k:'0' for k in d.FIELDS}
            r.update(event='retire',order=str(order),cycle=str(order),pc=f'{pc:x}',insn=f'{insn:x}')
            if gprs:r.update(rd=str(gprs[0][0]),rd_wdata=f'{gprs[0][1]:x}')
            writes=[(a,v) for a,v in accesses if v is not None]
            if writes and insn&127!=0x27:
                d.require(len(writes)==1,'Multiple scalar stores')
                a,v=writes[0]
                width=d.ref.base.compressed_memory(insn)['size'] if insn&3!=3 else 1<<((insn>>12)&7)
                r.update(mem_addr=f'{a:x}',mem_wmask=f'{((1<<width)-1)<<(a%8):x}',mem_wdata=f'{v:x}')
                if a==s['tohost']:htif.append(v)
            c.row(r);order+=1
    d.require(partial==1 and htif==[1] and c.exits==[],'Actual reference endpoint differs')
    # Only this Host-only endpoint bridge differs from a DUT Checker.finish().
    c.exits=[0]
    result=c.finish()
    verify(pins)
    return dict(status='HOST_EXISTING_SPIKE_ROW_ADAPTER_PASS_NOT_DUT',member=member,
                source_raw_sha256=ready['outputs']['spike.trace'],actual_endpoint=dict(HTIF=htif),
                endpoint_bridge='validated HTIF1 substitutes CTRL0 for Host finish test only',
                synthetic_cycle_order=True,partial_not_retired=partial,checks=result['checks'],
                scalar_commits=order,saved_csrs=c.saved,traps=c.traps,actions=c.actions,
                complete_finish_checks=True,restore_readback_checks=result['restore_readback_checks'])


def negatives():
    s=read(HERE/'reference_load01/soc.symbols.json');tested=[]
    def row(order=0,cycle=0):
        r={k:'0' for k in d.FIELDS};r.update(event='retire',order=str(order),cycle=str(cycle),pc='1000',insn='13');return r
    for name,bad in [('retire_gap',row(2,1)),('retire_duplicate',row(0,1)),('cycle_regressed',row(1,0))]:
        c=d.Checker(s,0);c.row(row(0,1))
        try:c.row(bad)
        except ValueError:tested.append(name);continue
        raise ValueError('Accepted '+name)
    c=d.Checker(s,0);c.calls=len(c.gold);c.saved[0x180]=123;c.regs[10]=c.regs[11]=0
    r=row();r['pc']=f'{s["check"]:x}'
    try:c.row(r)
    except ValueError:tested.append('saved_CSR_mismatch')
    else:raise ValueError('Accepted restored CSR mismatch')
    c=d.Checker(s,0);c.capture={7:0}
    r=row();r.update(pc=f'{s["mt_trap_vstart_read"]:x}',insn='802373',rd='6')
    try:c.row(r)
    except ValueError:tested.append('duplicate_handler_CSR')
    else:raise ValueError('Accepted duplicate handler CSR')
    return tested


if __name__=='__main__':
    out=HERE/'host_actual_reference_bridge02';out.mkdir(exist_ok=False)
    try:
        result=dict(status='HOST_ADAPTER_PASS_NOT_DUT',members=[analyze(m) for m in ('load',)],
                    negatives=negatives(),checker_sha256=receipt.sha(Path(d.__file__)),
                    bridge_sha256=receipt.sha(Path(__file__)))
    except BaseException as e:
        receipt.save(out/'not_accepted.json',dict(status='HOST_ADAPTER_NOT_ACCEPTED',error=f'{type(e).__name__}: {e}'))
        raise
    receipt.save(out/'result.json',result)
    print(json.dumps(result,indent=2))
