"""Actual-ELF ordered helper/setup/oracle audit, shared by Spike and VCS ports."""
from collections import Counter
import re
from model import NAME, BOUND, CAP, model, require
from software_prepare import disassemble
VETO=re.compile(r'RVV_FP_COMPARE_(?:DETAIL|FAIL|CAPACITY_FAIL)|BOARD_\w*(?:FAIL|TRAP|MISMATCH)|\b(?:ABORTED|FAILED|MISMATCH|TRAP)\b',re.I)
def rvv(c): return c&127==87 or c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)
def csr(c): return c&127==115 and bool((c>>12)&7)
def specification(elf,spike=False):
    s,_=disassemble(elf); fs=s['functions']; code=s['code']
    routines=[fs['op_'+str(i)] for i in range(10)]
    require([len(r) for r in routines]==[17]*4+[19]*6,'Original helper sizes')
    require(routines[4][10]['insn']=='62805c57' and routines[4][7]['insn']=='f2038053','Unboxed target encoding')
    body=fs[NAME+'_main']
    def unique(enc):
        hit=[r for r in body if r['insn']==enc];require(len(hit)==1,'Unique actual source PC '+enc);return hit[0]['pc']
    sites={n:unique(e) for n,e in dict(mask='00e60023',a='00f69023',b='fef71f23',output='00c68023',
        bits='0006c683',guard1='0017c783').items()}
    guard0=[r for r in body if r['text'].startswith('lbu\ta3,') and '<output>' in r['text']]
    require(len(guard0)==1,'Guard0 actual PC'); sites['guard0']=guard0[0]['pc']
    prel=[r for f in ('_start','main') for r in fs[f] if csr(int(r['insn'],16))]
    require(len(prel)==6 and [r['insn'] for r in prel[:5]]==['30401073','30529073','3002a073','00305073','00805073'],'Bootstrap CSR exact')
    stores=[r for r in fs['replay_exit'] if r['text'].startswith('sd\t')];require(len(stores)==1,'One exit store')
    park=[r for r in fs['replay_exit'] if r['pc']>stores[0]['pc']];require(len(park)==1 and park[0]['insn']=='a001','Exit park')
    return dict(**s,routines=routines,capacity=fs['capacity'],sites=sites,prelude=prel,spike=spike,
        exit_store=stores[0],park=park[0],exit_address=s['symbols']['tohost'] if spike else 0xd0000000)

def setup(s,g):
    a=s['symbols'];p=s['sites']
    for i,v in enumerate(g['mask']):yield p['mask'],a['mask']+i,v,1
    for i in range(16):
        yield p['a'],a['a']+2*i,g['a'][i],2
        yield p['b'],a['b']+2*i,g['b'][i],2
    for i in range(130):yield p['output'],a['output']+i,91,1

def audit(rows,s,spike_vectors=False):
    golds=model()['rows'];a=s['symbols'];sites=s['sites'];code=s['code']
    lookup={r['pc']:(op,i) for op,rr in enumerate(s['routines']) for i,r in enumerate(rr)}
    unused=[(rr[0]['pc'],rr[-1]['pc']+len(rr[-1]['insn'])//2) for rr in s['routines'][5:]]
    regs={0:0};vectors={};csrs={};memory={};counts=Counter();sitecounts=Counter()
    step=capstep=prestep=pos=retired=parks=0;current=None;calls=[];exited=False;lastcycle=-1
    events=list(setup(s,golds[0]));console=bytearray(8192);firmware_to_exit=None
    caplookup={r['pc']:i for i,r in enumerate(s['capacity'])}
    setpcs={sites[n] for n in ('mask','a','b','output')};readpcs={sites[n] for n in ('bits','guard0','guard1')}
    def finish():
        if current is not None:
            require(step==0 and current['reads']==18,'Missing complete16 bits+2 guards or helper')
            require(current['vstart']==0 and current['flags']==golds[len(calls)-1]['flags'],'Missing CSR oracle')
    for row in rows:
        require(row.get('trap',0)==0,'Unexpected trap')
        cycle=row.get('cycle',retired);require(cycle>=lastcycle,'Cycle reversal');lastcycle=cycle
        if row.get('event','retire')!='retire':
            require(row['event']!='cvx_exception','CVX exception');continue
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
            if i==1:require((rd,value)==(10,16),'Actual capacity16')
            capstep+=1
        if rvv(c):require(pair is not None or pc==s['capacity'][1]['pc'],'RVV outside source windows')
        if pc in setpcs:
            require(capstep==3 and prestep==6 and step==0,'Setup phase')
            finish();require(pos<len(events),'Unexpected setup count')
            ep,ea,ev,width=events[pos]
            require((pc,address,wdata&((1<<(8*width))-1),wmask)==(ep,ea,ev,((1<<width)-1)<<(ea%8)),'Original setup order/value/BE')
            for b in range(width):memory[address+b]=(wdata>>(8*b))&255
            pos+=1;sitecounts[pc]+=1
        elif wmask and c&127!=39:
            areas=[(a[n],a[n]+size) for n,size in [('a',2048),('b',2048),('mask',128),('output',130)]]
            require(not any(lo<=address<hi for lo,hi in areas) or pc<a['trap_entry'] and not calls and pos==0,'Unexpected write into original arrays')
        if pair is not None:
            op,i=pair;require(op<5 and i==step and capstep==3 and prestep==6,'Helper entry/order/phase')
            rr=s['routines'][op];delta=2 if op>=4 else 0
            if i==0:
                finish();j=len(calls);require(j<265 and pos==len(events),'Full setup/extra call')
                g=golds[j];require(op==g['op'],'Original operation order')
                args=[a['a'],a['b'],a['output']+1,g['vl'],16,a['mask'],0,g['sticky']]
                require([regs.get(n) for n in range(10,18)]==args,'Original eight arguments')
                require((rd,value)==(30,0),'Save prior flags0')
                current=dict(ordinal=j+1,op=op,vl=g['vl'],mode=g['mode'],sticky=g['sticky'],reads=0,vstart=None,flags=None)
                calls.append(current)
            g=golds[len(calls)-1]
            if i in (1,6+delta,14+delta):require((rd,value)==(5,g['vl'] if i==6+delta else 16),'Original vset return')
            if op==4 and i==6:
                require((rd,value)==(7,0) and address==a['b'] and rmask==3<<(address%8),'Original unboxed LHU')
            if op==4 and i==7:
                require(regs.get(7)==0,'Unboxed scalar GPR');require(not row.get('fp') or row['fp'].get(0)==0,'Actual fmv.d.x payload')
            if i==7+delta:require(regs.get(17)==g['sticky'],'Set original sticky flags')
            if i==8+delta:
                current['target']=dict(pc=hex(pc),encoding=ins['insn'],cycle=cycle,retired=retired)
                if spike_vectors:
                    require(csrs.get('vl')==g['vl'] and csrs.get('vtype')==14 and csrs.get('vstart')==0,'Actual target CSR')
                    for n,vals in ((8,g['a']),(16,g['b'])):
                        require(n in vectors and [vectors[n]>>(16*k)&65535 for k in range(16)]==vals,'Actual source vector')
                    require(vectors.get(24,-1)&65535==0x5b5b and vectors.get(0,-1)&65535==g['mask'][0]*257,'Actual mask/destination setup')
            if i==9+delta:require((rd,value)==(10,0),'Returned vstart');current['vstart']=value
            if i==10+delta:require((rd,value)==(6,g['flags']),'Actual fflags mismatch');current['flags']=value
            if i==12+delta:require((rd,value)==(10,g['flags']<<32),'Packed status mismatch')
            if i==13+delta:require(regs.get(30)==0,'Restore prior flags')
            if i==15+delta:
                require(regs.get(12)==a['output']+1,'Full-mask store pointer')
                if spike_vectors:
                    writes=row.get('accesses',[]);require(len(writes)==2,'Complete packed mask store')
                    for k,(addr,v) in enumerate(writes):
                        require(addr==a['output']+1+k and v is not None,'Store address/value')
                        require(all((v>>b)&1 in g['allowed'][k*8+b] for b in range(8)),'Actual vector store result')
            counts[op,i]+=1;step=(step+1)%len(rr)
        if pc in readpcs:
            require(current is not None and step==0,'Scalar oracle phase')
            k=current['reads'];require(k<18,'Extra oracle reads')
            expected_pc=sites['bits'] if k<16 else sites['guard0' if k==16 else 'guard1']
            addr=a['output']+(1+k//8 if k<16 else 0 if k==16 else 3)
            require(pc==expected_pc and address==addr and rmask==1<<(addr%8) and rd==(c>>7)&31 and not wmask,'Full oracle PC/address/order/LBU')
            require(value<=255,'LBU width')
            if k<16:require((value>>(k%8))&1 in g['allowed'][k],'Result bit mismatch')
            else:require(value==91,'Guard mismatch')
            current['reads']+=1
            if current['reads']==18:
                events=list(setup(s,golds[len(calls)])) if len(calls)<265 else [];pos=0
        elif rmask and a['output']<=address<a['output']+130:
            require(pair is not None,'Unexpected output read outside oracle')
        # Full vector payload checks apply only to raw reference, not scalar DUT CSV.
        vectors.update(row.get('vectors',{}));csrs.update(row.get('csrs',{}))
        if spike_vectors and pair is not None and pair[1]==8+(2 if pair[0]>=4 else 0):
            require(24 in vectors and all((vectors[24]>>k)&1 in g['allowed'][k] for k in range(16)),'Actual reference result vector')
        if s['spike'] and wmask and a['replay_log']<=address<a['replay_log']+8192:
            console[address-a['replay_log']]=wdata&255
        if pc==s['exit_store']['pc'] or address==s['exit_address'] and wmask:
            require(pc==s['exit_store']['pc'] and address==s['exit_address'] and wmask==255 and wdata==int(s['spike']),'Actual exit0')
            finish();require(len(calls)==265,'Incomplete prefix');exited=True;firmware_to_exit=retired
        if rd:regs[rd]=value
    finish()
    require(exited and prestep==6 and capstep==3 and len(calls)==265,'Missing completed scope/exit')
    require(all(counts[op,i]==(56 if op<4 else 41) for op in range(5) for i in range(len(s['routines'][op]))),'Original exact helper multiplicities')
    return dict(status='PASS_RAW_ORIGINAL265_NOT_FULL_PARENT',target_calls=265,full_result_bit_checks=4240,guard_checks=530,
        returned_vstart_zero=265,returned_flags_checked=265,helper_instructions=sum(counts.values()),unused_helper_retirements=0,
        actual_initialization_stores=sum(sitecounts.values()),firmware_retired_to_exit=firmware_to_exit,retired=retired,park_retired=parks,
        calls=calls,full_reference_vectors=spike_vectors,reconstructed_console=console.split(b'\0',1)[0].decode('ascii'))

def spike_rows(path):
    pattern=re.compile(r'core\s+0:\s+\d\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)')
    boot=[(0x1000,0x297),(0x1004,0x02028593),(0x1008,0xf1402573),(0x100c,0x0182b283),(0x1010,0x28067)]
    nboot=0
    with path.open() as stream:
        for line in stream:
            require('trap_' not in line,'Spike trap');m=pattern.fullmatch(line.strip());require(m is not None,'Unparsed raw record')
            pc,c,rest=int(m[1],16),int(m[2],16),m[3]
            if pc<0x80000000:
                require(nboot<5 and (pc,c)==boot[nboot],'Exact reset ROM');nboot+=1;continue
            require(nboot==5,'Missing reset ROM')
            rd=re.search(r'\bx(\d+)\s+0x([0-9a-f]+)',rest)
            accesses=[(int(x,16),int(v,16) if v else None) for x,v in re.findall(r'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?',rest)]
            address=rmask=wmask=wdata=0
            if c&127 in (3,35) and accesses:
                address,val=accesses[0];width=1<<(((c>>12)&7)%4)
                if val is None:rmask=((1<<width)-1)<<(address%8)
                else:wmask=((1<<width)-1)<<(address%8);wdata=val
            yield dict(pc=pc,insn=c,rd=int(rd[1]) if rd else 0,value=int(rd[2],16) if rd else 0,address=address,
                rmask=rmask,wmask=wmask,wdata=wdata,accesses=accesses,
                vectors={int(n):int(v,16) for n,v in re.findall(r'\bv(\d+)\s+0x([0-9a-f]+)',rest)},
                fp={int(n):int(v,16) for n,v in re.findall(r'\bf(\d+)\s+0x([0-9a-f]+)',rest)},
                csrs={n:int(v,16) for n,v in re.findall(r'\bc\d+_(vl|vtype|vstart)\s+0x([0-9a-f]+)',rest)})
