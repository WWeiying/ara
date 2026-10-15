"""Small corrected BSS gate regression only; never reads reference raw."""
import json
from pathlib import Path
from bss_guard import BSSGuard

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

if __name__ == '__main__':
    result=synthetic()
    result.update(status='PASS_REFERENCE_BSS_HOST_ONLY',raw_reads=0)
    with (Path(__file__).resolve().parent/'reference_gate_host.json').open('x') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],len(result['negatives']))
