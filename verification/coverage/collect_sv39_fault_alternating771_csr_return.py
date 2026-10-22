"""Offline exact handler CSR-write/return proof, keeping both prior HOLDs."""
import argparse
import inspect
from pathlib import Path
import collect_sv39_fault_alternating771_terminal_prefix as prefix

old=prefix.old
life,require=prefix.life,prefix.require

def handler_replay(rows,reference,s):
    retired=[r for r in rows if r['event']=='retire' and not int(r['trap'])]
    indexed=[(j,c) for j,c in enumerate(reference) if c.pc not in (s['fault_load_pc'],s['fault_store_pc'])]
    expected=[c for j,c in indexed]
    require(len(retired)==len(expected),'Complete handler scalar alignment')
    registers={i:0 for i in range(32)};context=None;phase=0;proof=[];entries=0
    for i,(r,c) in enumerate(zip(retired,expected)):
        pc,insn=int(r['pc'],16),int(r['insn'],16)
        require((pc,insn)==(c.pc,c.instruction),'Every scalar PC/opcode')
        rd=int(r['rd']);value=int(r['rd_wdata'],16)
        require(({rd:value} if rd else {})=={k:v for k,v in c.gpr_writes.items() if k},'Every scalar GPR value')
        if pc==0x800025c2:
            require(insn==0x34129073 and registers[5]==s['fault_load_pc'] and context is None,
              'Exact phase-entry mepc PC/encoding/source value')
            entries+=1
        if pc==s['fault_handler']:
            require(context is None and phase<12,'Unique handler ownership')
            cause=(13,15,9)[phase%3];faultpc=s['fault_load_pc'] if phase%3==0 else s['fault_store_pc']
            epc=s['fault_s_ecall'] if cause==9 else faultpc
            context=dict(phase=phase,cause=cause,epc=epc,reads=[],writes=[],target=None)
        if context is not None and insn&0x7f==0x73:
            csr=insn>>20;funct=(insn>>12)&7;rs=(insn>>15)&31
            if csr in (0x341,0x342,0x343,8,0xc20,0xc21) and funct in (1,2,3,5,6,7):
                writing=funct in (1,5) or rs!=0
                if writing:
                    require(csr==0x341 and funct==1 and rd==0 and not context['writes'],
                      'Only one exact mepc CSRRW, no cause/tval/other CSR writes')
                    required=[0x342,0x341] if context['cause']==9 else [0x342,0x341,0x343,8,0xc20,0xc21]
                    require(context['reads']==required,'No early mepc write before complete trap observation')
                    target=s['fault_resume'] if context['cause']==9 else context['epc']+4
                    require(pc==(0x800020aa if context['cause']==9 else 0x80002070) and
                      insn==0x34129073 and registers[rs]==target,'Exact source-bound mepc PC/encoding/GPR')
                    context['writes'].append(dict(pc=pc,value=target));context['target']=target
                else:
                    values={0x342:context['cause'],0x341:context['epc'],
                      0x343:old.p.ADDRESSES[(phase//3)&1],8:0,0xc20:1,0xc21:24}
                    require(rd!=0 and csr not in context['reads'] and not context['writes'] and
                      value==values[csr],'Exact prewrite trap CSR read')
                    context['reads'].append(csr)
            if insn==0x30200073:
                ref_index=indexed[i][0]
                # Spike logs S-ecall as an exception, not a commit. The actual
                # RVFI trap below binds that missing commit to the exact target.
                next_ref=s['fault_handler'] if context['cause']==15 else context['target']
                require(len(context['writes'])==1 and i+1<len(retired) and ref_index+1<len(reference) and
                  reference[ref_index+1].pc==next_ref and
                  pc==(0x800020ae if context['cause']==9 else 0x80002074),
                  'Exact MRET PC and source reference next target')
                if context['cause']==9:
                    require(int(retired[i+1]['pc'],16)==context['target'],'Exact scalar resume return')
                    context['return_evidence']='Actual RVFI scalar resume PC'
                else:
                    require(int(retired[i+1]['pc'],16)==s['fault_handler'],'Expected next precise trap handler')
                    interval=[x for x in rows if int(r['cycle'])<int(x['cycle'])<int(retired[i+1]['cycle'])]
                    if context['cause']==13:
                        owners=[x for x in interval if x['event']=='arch_start']
                        require(len(owners)==1 and int(owners[0]['insn'],16)==reference[ref_index+1].instruction,
                          'Returned fault-store actual architecture owner, not synthetic zero PC')
                        responses=[x for x in interval if x['event']=='cvx_resp']
                        require(len(responses)==1 and int(responses[0]['trans_id'])==int(owners[0]['trans_id']) and
                          int(responses[0]['trap'])==1,'Returned fault-store exception conservation')
                        context['return_evidence']='Actual store arch_start/exception + next handler exact mepc; arch_start PC is0 placeholder'
                    else:
                        traps=[x for x in interval if x['event']=='retire' and int(x['trap'])]
                        require(len(traps)==1 and int(traps[0]['pc'],16)==context['target'] and
                          int(traps[0]['insn'],16)==0x73 and int(traps[0]['rd'])==0 and
                          int(traps[0]['mem_wmask'],16)==int(traps[0]['mem_rmask'],16)==0,'Exact returned S-ecall')
                        context['return_evidence']='Actual precise S-ecall trap RVFI PC'
                proof.append(context);context=None;phase+=1
        if rd:registers[rd]=value
        registers[0]=0
    require(context is None and phase==12 and entries==4,'All8fault,4ecall and4phase entries complete')
    return proof

def collect(output):
    require(life.digest(Path(old.__file__))==prefix.OLD_SHA,'Original frozen collector drift')
    manifest=life.read_bound(prefix.RUN.with_name(prefix.RUN.name+'.prepared.json'),prefix.RUN_SHA)
    life.check(manifest['pins']);manifest=dict(manifest,pins=dict(manifest['pins']))
    for path in (Path(__file__).resolve(),Path(prefix.__file__).resolve(),
      Path(__file__).with_name('test_collect_sv39_fault_csr_return.py'),
      Path(prefix.__file__).with_name('test_collect_sv39_fault_terminal_prefix.py')):
        manifest['pins']=life.merge_pins(manifest['pins'],{str(path):life.digest(path)})
    for name in (prefix.RUN.name+'-qualified','sv39-fault-alternating-terminal-prefix-qualified771-agent-20261007-01'):
        path=life.OUT/name/'failure.json';manifest['pins']=life.merge_pins(manifest['pins'],{str(path):life.digest(path)})
    source=inspect.getsource(old.collect)
    needle="entry=next(i for i,c in enumerate(reference) if c.pc==0x80000000)\n        reference=reference[entry:]\n        require(reference[-1].memory_accesses==((s['tohost'],1),),'Complete entry-tohost reference')"
    require(source.count(needle)==1,'Exact prefix predecessor gate')
    source=source.replace(needle,'reference=terminal_prefix(reference,s)')
    gate="aligned=scalar['aligned_vector_faults'];require(len(aligned)==8,'Exact aligned page faults')"
    require(source.count(gate)==1,'Exact full scalar prerequisite')
    source=source.replace(gate,gate+"\n        handler_proof=handler_replay(rows,reference,s)\n        life.save(qualified/'handler-return-proof.json',handler_proof)")
    oldgate="and f['fault_handler_returned'] and not f['invalidated_fault_csrs']"
    require(source.count(oldgate)==1,'Exact invalidation gate')
    source=source.replace(oldgate,"and f['fault_handler_returned'] and f['invalidated_fault_csrs']==['0x341']")
    source=source.replace("qualified=out.with_name(out.name+'-qualified')",'qualified=OUTPUT')
    namespace=dict(old.collect.__globals__,terminal_prefix=prefix.terminal_prefix,handler_replay=handler_replay,OUTPUT=output)
    exec(compile(source,str(Path(__file__).resolve())+':private-source-bound-successor','exec'),namespace)
    namespace['collect'](prefix.RUN,manifest)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    collect(p.parse_args().output.resolve())
