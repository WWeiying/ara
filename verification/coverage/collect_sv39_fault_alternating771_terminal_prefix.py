"""Offline successor: exact successful CRT terminal and side-effect-free spin."""
import argparse
import inspect
from pathlib import Path
import run_sv39_fault_alternating771 as old

life,require=old.life,old.require
OLD_SHA='173ab2fe82415b5c322d29e3ab80bff9181c81ae852c5c9d9fda81e78e3cbd27'
RUN=life.OUT/'sv39-fault-alternating-old-image771-agent-20261007-02'
RUN_SHA='5d2f2330103dbd0a4a97ada621286fec45918e0df43772d38e58a8a93dc810f1'

def terminal_prefix(commits,s):
    entry=[i for i,c in enumerate(commits) if c.pc==0x80000000]
    require(len(entry)==1,'Unique ELF entry')
    terminals=[(i,c) for i,c in enumerate(commits) if any(a==s['tohost'] for a,v in c.memory_accesses)]
    require(len(terminals)==1,'Unique tohost access')
    index,last=terminals[0]
    require(index>entry[0]+2 and last.pc==0x8000007a and last.instruction==0x00a2b023 and
      last.memory_accesses==((s['tohost'],1),) and not
      (last.gpr_writes or last.fpr_writes or last.vector_writes or last.csr_writes),'Exact CRT successful terminal store')
    require([c.pc for c in commits[index-2:index]]==[0x80000072,0x80000076],
      'Terminal preceded by actual frozen CRT finish sequence, not premature tohost')
    prefix=commits[entry[0]:index+1]
    writes={a:v for c in prefix for a,v in c.memory_accesses if v is not None}
    require([writes.get(s['g75_result']+4*i) for i in range(2)]==[1091,0] and
      writes.get(s['fault_count'])==8 and writes.get(s['fault_returns'])==4,
      'Terminal after complete fault/check ledger')
    for c in commits[index+1:]:
        require(c.pc==0x8000007e and c.instruction==0xa001 and not
          (c.gpr_writes or c.fpr_writes or c.vector_writes or c.csr_writes or c.memory_accesses),
          'After-terminal only exact source-bound self-jump with no architectural effects')
    return prefix

def collect(output):
    require(life.digest(Path(old.__file__))==OLD_SHA,'Frozen collector changed')
    manifest=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SHA)
    life.check(manifest['pins'])
    manifest=dict(manifest,pins=dict(manifest['pins']))
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_sv39_fault_terminal_prefix.py')):
        manifest['pins']=life.merge_pins(manifest['pins'],{str(path):life.digest(path)})
    prior_failure=RUN.with_name(RUN.name+'-qualified')/'failure.json'
    manifest['pins']=life.merge_pins(manifest['pins'],{str(prior_failure):life.digest(prior_failure)})
    source=inspect.getsource(old.collect)
    needle="entry=next(i for i,c in enumerate(reference) if c.pc==0x80000000)\n        reference=reference[entry:]\n        require(reference[-1].memory_accesses==((s['tohost'],1),),'Complete entry-tohost reference')"
    require(source.count(needle)==1,'Exact frozen reference gate')
    source=source.replace(needle,'reference=terminal_prefix(reference,s)')
    destination="qualified=out.with_name(out.name+'-qualified')"
    require(source.count(destination)==1,'Unique output binding')
    source=source.replace(destination,'qualified=OUTPUT')
    namespace=dict(old.collect.__globals__,terminal_prefix=terminal_prefix,OUTPUT=output)
    exec(compile(source,str(Path(__file__).resolve())+':exact-private-successor','exec'),namespace)
    namespace['collect'](RUN,manifest)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    collect(p.parse_args().output.resolve())
