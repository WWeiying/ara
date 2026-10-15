#!/usr/bin/env python3
"""Bounded Host and original startup-prefix evidence only; no whole raw parse."""
import hashlib
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from prepare import read,save,sha,SHAPES
from bss_guard import BSSGuard
DECODER=ROOT.parents[3]/'coverage/scoped_rv64c_memory.py'

def synthetic():
    symbols=dict(_start=0x80000000,trap_entry=0x80000054,main=0x80000100,
        __bss_start=0x80002000,__bss_end=0x80004010,replay_log=0x80002008)
    code={0x80000046:0x0002b023}
    def fresh():return BSSGuard(symbols,code)
    def clear(g):
        for a in range(g.begin,g.end,8):g.store(g.store_pc,0x0002b023,a,0,8,{0:0,5:a,6:g.end},0)
        g.pc(symbols['main'])
    g=fresh();clear(g);g.store(symbols['main']+4,0x00b50023,g.log,65,1,{},0);g.finish()
    negatives={}
    def reject(name,fn):
        try:fn()
        except ValueError:negatives[name]=True
        else:raise ValueError('Missed Host negative '+name)
    def initial(value=0,pc=None,addr=None,width=8,t0=None,t1=None,calls=0):
        g=fresh();a=g.begin if addr is None else addr
        g.store(g.store_pc if pc is None else pc,0x0002b023,a,value,width,
                {0:0,5:a if t0 is None else t0,6:g.end if t1 is None else t1},calls)
    reject('nonzero_BSS',lambda:initial(value=1))
    reject('badPC_console_sd',lambda:initial(pc=0x80000048,addr=symbols['replay_log']))
    reject('out_of_range',lambda:initial(addr=symbols['__bss_end']))
    reject('cross_console_end',lambda:initial(addr=symbols['replay_log']+8192-4))
    reject('misaligned',lambda:initial(addr=symbols['__bss_start']+1))
    reject('wrong_t0',lambda:initial(t0=0))
    reject('wrong_t1',lambda:initial(t1=0))
    reject('prior_calls',lambda:initial(calls=1))
    reject('missing_BSS_beforemain',lambda:fresh().pc(symbols['main']))
    def runtimewide():
        g=fresh();clear(g);g.store(symbols['main']+4,0x0002b023,g.log,0,8,{},0)
    reject('runtime_wide_write',runtimewide)
    def restartafterprint():
        g=fresh();clear(g);g.store(symbols['main']+4,0x00b50023,g.log,65,1,{},0)
        g.store(g.store_pc,0x0002b023,g.begin,0,8,{0:0,5:g.begin,6:g.end},0)
    reject('postprint_reenter_BSS',restartafterprint)
    return dict(positive=1,negatives=negatives)

def first_rejected(p):
    root=ROOT/p['id'];proof=read(root/'sourceproof.json');s=proof['backends']['spike']['symbols'];regs={0:0}
    raw=root/'reference01/commits.log';before=raw.stat();context=[];found=None
    linepat=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rdpat=re.compile(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)');writepat=re.compile(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*$')
    with raw.open() as stream:
        for n,line in enumerate(stream,1):
            if n>20000:raise ValueError('Bounded startup-prefix probe missed; no full parse allowed')
            context.append(line.rstrip());context=context[-6:];m=linepat.match(line)
            if not m:continue
            pc,insn,rest=int(m[1],16),int(m[2],16),m[3];wr=writepat.search(rest)
            if wr:
                addr,val=int(wr[1],16),int(wr[2],16)
                if s['replay_log']<=addr<s['replay_log']+8192:
                    width=1<<((insn>>12)&7) if insn&127==35 else None
                    if not(pc==s['_start']+0x46 and insn==0x0002b023 and width==8 and val==0 and addr==s['replay_log'] and
                            regs.get(5)==addr and regs.get(6)==s['__bss_end']):raise ValueError('Actual rejected prefix differs')
                    found=dict(line=n,pc=hex(pc),insn=hex(insn),address=hex(addr),width=width,value=val,
                        t0=hex(regs[5]),t1=hex(regs[6]),bss_start=hex(s['__bss_start']),bss_end=hex(s['__bss_end']),
                        replay_log=hex(s['replay_log']),main=hex(s['main']),context=context)
                    break
            rd=rdpat.search(rest)
            if rd:regs[int(rd[1])]=int(rd[2],16)
    after=raw.stat()
    if found is None or (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('Prefix absent/raw changed')
    return found

def main():
    result=synthetic();result.update(status='HOST_AND_BOUNDED_STARTUP_PROBE_PASS_NOT_FULL_REFERENCE',
        first_rejected={p['id']:first_rejected(p) for p in SHAPES},complete_raw_parses=0,
        pins={str(p):sha(p) for p in (HERE/'bss_guard.py',HERE/'test_host.py',HERE/'checker.py',DECODER,
            ROOT/'runtime/startup.S',ROOT/'runtime/replay.ld',ROOT/'runtime/runtime.c')})
    save(HERE/'host.json',result)
    print(json.dumps(dict(status=result['status'],positive=result['positive'],negative=len(result['negatives']),
        first_rejected={k:{n:v[n] for n in ('line','pc','insn','width','value','address')} for k,v in result['first_rejected'].items()})))

if __name__=='__main__':main()
