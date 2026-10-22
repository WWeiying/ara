"""Mature FP ordered scalar checker adapted only for alias50/CAP512/op0."""
from collections import Counter
import re
from model import NAME, BOUND, CAP, model, require
from elf import disassemble
VETO=re.compile(r'RVV_FP_COMPARE_(?:DETAIL|FAIL|CAPACITY_FAIL)|BOARD_\w*(?:FAIL|TRAP|MISMATCH)|\b(?:ABORTED|FAILED|MISMATCH|TRAP)\b',re.I)
def rvv(c): return c&127==87 or c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)
def csr(c): return c&127==115 and bool((c>>12)&7)
def specification(elf):
    s,_=disassemble(elf); fs=s['functions']; code=s['code']
    routines=[fs['op_'+str(i)] for i in range(10)]
    require([len(r) for r in routines]==[16]*4+[21]*6,'Original alias helper sizes')
    require(routines[0][7]['insn']=='62881457','Actual unmasked vmfeq v8 alias target')
    require([r['insn'] for r in fs['capacity']]==['52fd','00b2f557','8082'],'Actual e16/m8 capacity3')
    body=fs[NAME+'_main']
    def unique(enc):
        hit=[r for r in body if r['insn']==enc];require(len(hit)==1,'Unique actual source PC '+enc);return hit[0]['pc']
    sites={n:unique(e) for n,e in dict(mask='00e58023',a='00f69023',b='fef71f23',output='00c68023',
        bits='0006c683',guard1='0017c783').items()}
    guard0=[r for r in body if r['text'].startswith('lbu\ta3,') and '<output>' in r['text']]
    require(len(guard0)==1,'Guard0 actual PC'); sites['guard0']=guard0[0]['pc']
    prel=[r for f in ('_start','main') for r in fs[f] if csr(int(r['insn'],16))]
    require(len(prel)==6 and [r['insn'] for r in prel[:5]]==['30401073','30529073','3002a073','00305073','00805073'],'Bootstrap CSR exact')
    stores=[r for r in fs['replay_exit'] if r['text'].startswith('sd\t')];require(len(stores)==1,'One exit store')
    park=[r for r in fs['replay_exit'] if r['pc']>stores[0]['pc']];require(len(park)==1 and park[0]['insn']=='a001','Exit park')
    return dict(**s,routines=routines,capacity=fs['capacity'],sites=sites,prelude=prel,spike=False,
        exit_store=stores[0],park=park[0],exit_address=0xd0000000)

def setup(s,g):
    a=s['symbols'];p=s['sites']
    for i,v in enumerate(g['mask']):yield p['mask'],a['mask']+i,v,1
    for i in range(CAP):
        yield p['a'],a['a']+2*i,g['a'][i],2
        yield p['b'],a['b']+2*i,g['b'][i],2
    for i in range(130):yield p['output'],a['output']+i,91,1

def audit(rows,s):
    golds=model()['rows'];a=s['symbols'];sites=s['sites'];code=s['code']
    lookup={r['pc']:(op,i) for op,rr in enumerate(s['routines']) for i,r in enumerate(rr)}
    unused=[(rr[0]['pc'],rr[-1]['pc']+len(rr[-1]['insn'])//2) for rr in s['routines'][1:]]
    regs={0:0};counts=Counter();sitecounts=Counter()
    step=capstep=prestep=pos=retired=parks=0;current=None;calls=[];exited=False;lastcycle=-1
    events=list(setup(s,golds[0]));firmware_to_exit=None
    caplookup={r['pc']:i for i,r in enumerate(s['capacity'])}
    setpcs={sites[n] for n in ('mask','a','b','output')};readpcs={sites[n] for n in ('bits','guard0','guard1')}
    def finish():
        if current is not None:
            require(step==0 and current['reads']==CAP+2,'Missing complete512 bits+2 guards or helper')
            require(current['vstart']==0 and current['flags']==golds[len(calls)-1]['flags'],'Missing CSR oracle')
    for row in rows:
        require(row.get('trap',0)==0,'Unexpected trap')
        cycle=row.get('cycle',retired);require(cycle>=lastcycle,'Cycle reversal');lastcycle=cycle
        if row.get('event','retire')!='retire':
            require(row['event'] in ('cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'),'Unknown event/exception');continue
        require(row.get('order',retired)==retired,'Retirement order')
        pc,c,rd,value=[row.get(k,0) for k in ('pc','insn','rd','value')]
        ins=code.get(f'{pc:x}');require(ins is not None and int(ins['insn'],16)==c,'Actual ELF PC/code')
        retired+=1
        address,rmask,wmask,wdata=[row.get(k,0) for k in ('address','rmask','wmask','wdata')]
        if exited:
            require(pc==s['park']['pc'] and not(rd or rmask or wmask),'Post-HTIF only original parking')
            parks+=1;continue
        require(pc!=a['trap_entry'] and not any(lo<=pc<hi for lo,hi in unused),'Unused helper/trap PC range')
        if step:require(pc==s['routines'][golds[len(calls)-1]['op']][step]['pc'],'Noncontiguous helper window')
        if 0<capstep<3:require(pc==s['capacity'][capstep]['pc'],'Noncontiguous capacity')
        pair=lookup.get(pc)
        if csr(c) and pair is None:
            require(prestep<6 and pc==s['prelude'][prestep]['pc'] and not calls and not capstep,'CSR outside bootstrap phase')
            if prestep<5:
                src=(c>>15)&31;operand=src if c&(1<<14) else regs.get(src)
                require(operand==[0,a['trap_entry'],0x6600,0,0][prestep] and rd==0,'Bootstrap CSR operand')
            else:require(value==128 and rd==(c>>7)&31,'vlenb exact')
            prestep+=1
        if pc in caplookup:
            i=caplookup[pc];require(i==capstep and prestep==6 and not calls,'Capacity once phase')
            if i==0:require((rd,value)==(5,(1<<64)-1),'Capacity AVL')
            if i==1:require((rd,value)==(10,CAP),'Actual capacity512')
            capstep+=1
        if rvv(c):require(pair is not None or pc==s['capacity'][1]['pc'],'RVV outside source windows')
        if pc in setpcs:
            require(capstep==3 and prestep==6 and step==0,'Setup phase')
            finish();require(pos<len(events),'Unexpected setup count')
            ep,ea,ev,width=events[pos]
            require((pc,address,wdata&((1<<(8*width))-1),wmask)==(ep,ea,ev,((1<<width)-1)<<(ea%8)),'Original setup order/value/BE')
            pos+=1;sitecounts[pc]+=1
        elif wmask and c&127!=39:
            areas=[(a[n],a[n]+size) for n,size in [('a',2048),('b',2048),('mask',128),('output',130)]]
            require(not any(lo<=address<hi for lo,hi in areas) or pc<a['trap_entry'] and not calls and pos==0,'Unexpected write into original arrays')
        if pair is not None:
            op,i=pair;require(op==0 and i==step and capstep==3 and prestep==6,'Helper entry/order/phase')
            rr=s['routines'][op]
            if i==0:
                finish();j=len(calls);require(j<BOUND and pos==len(events),'Full setup/extra call')
                g=golds[j];require(op==g['op'],'Original operation order')
                args=[a['a'],a['b'],a['output']+1,g['vl'],CAP,a['mask'],0,g['sticky']]
                require([regs.get(n) for n in range(10,18)]==args,'Original eight arguments')
                require((rd,value)==(30,0),'Save prior flags0')
                current=dict(ordinal=j+1,op=op,vl=g['vl'],mode=g['mode'],sticky=g['sticky'],reads=0,vstart=None,flags=None)
                calls.append(current)
            g=golds[len(calls)-1]
            if i in (1,5,13):require((rd,value)==(5,g['vl'] if i==5 else CAP),'Original vset return')
            if i==6:require(rd==0 and regs.get(17)==g['sticky'],'Set original sticky flags')
            if i==7:
                current['target']=dict(pc=hex(pc),encoding=ins['insn'],cycle=cycle,retired=retired)
            if i==8:require((rd,value)==(10,0),'Returned vstart');current['vstart']=value
            if i==9:require((rd,value)==(6,g['flags']),'Actual fflags mismatch');current['flags']=value
            if i==10:require((rd,value)==(6,g['flags']<<32),'Shift actual flags')
            if i==11:require((rd,value)==(10,g['flags']<<32),'Packed status mismatch')
            if i==12:require(rd==0 and regs.get(30)==0,'Restore prior flags')
            if i==14:
                require(regs.get(12)==a['output']+1,'Full-mask store pointer')
            counts[op,i]+=1;step=(step+1)%len(rr)
        if pc in readpcs:
            require(current is not None and step==0,'Scalar oracle phase')
            k=current['reads'];require(k<CAP+2,'Extra oracle reads')
            expected_pc=sites['bits'] if k<CAP else sites['guard0' if k==CAP else 'guard1']
            addr=a['output']+(1+k//8 if k<CAP else 0 if k==CAP else 65)
            require(pc==expected_pc and address==addr and rmask==1<<(addr%8) and rd==(c>>7)&31 and not wmask,'Full oracle PC/address/order/LBU')
            require(value<=255,'LBU width')
            if k<CAP:require((value>>(k%8))&1 in g['allowed'][k],'Result bit mismatch')
            else:require(value==91,'Guard mismatch')
            current['reads']+=1
            if current['reads']==CAP+2:
                events=list(setup(s,golds[len(calls)])) if len(calls)<BOUND else [];pos=0
        elif rmask and a['output']<=address<a['output']+130:
            require(pair is not None,'Unexpected output read outside oracle')
        if pc==s['exit_store']['pc'] or address==s['exit_address'] and wmask:
            require(pc==s['exit_store']['pc'] and address==s['exit_address'] and wmask==255 and wdata==int(s['spike']),'Actual exit0')
            finish();require(len(calls)==BOUND,'Incomplete prefix');exited=True;firmware_to_exit=retired
        if rd:regs[rd]=value
    finish()
    require(exited and prestep==6 and capstep==3 and len(calls)==BOUND,'Missing completed scope/exit')
    require(all(counts[op,i]==(BOUND if op==0 else 0) for op in range(10) for i in range(len(s['routines'][op]))),'Original exact helper multiplicities')
    return dict(status='PASS_RAW_ORIGINAL_ALIAS50_NOT_FULL_PARENT',target_calls=BOUND,full_result_bit_checks=BOUND*CAP,guard_checks=BOUND*2,
        returned_vstart_zero=BOUND,returned_flags_checked=BOUND,helper_instructions=sum(counts.values()),unused_helper_retirements=0,
        actual_initialization_stores=sum(sitecounts.values()),firmware_retired_to_exit=firmware_to_exit,retired=retired,park_retired=parks,
        calls=calls,full_reference_vectors=False,source_scope='original first50, not682/full parent/Linux')
