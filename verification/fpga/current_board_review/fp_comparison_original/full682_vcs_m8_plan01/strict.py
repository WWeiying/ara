"""Exact682 ordered setup/helper/packed oracle; scalar DUT and full-vector Spike."""
from collections import Counter
import re
import sys
from pathlib import Path
from model import CAP, BOUND, model, require
from newscope import NAME, BASE, EVENTS
from elf import disassemble
sys.path.insert(0,str(BASE.parents[1]/'coverage'))
from scoped_rv64c_memory import decode as compressed_memory

VETO=re.compile(r'RVV_FP_COMPARE_(?:DETAIL|FAIL|CAPACITY_FAIL)|BOARD_\w*(?:FAIL|TRAP|MISMATCH)|\b(?:ABORTED|FAILED|MISMATCH|TRAP)\b',re.I)
def rvv(c):return c&127==87 or c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)
def csr(c):return c&127==115 and bool((c>>12)&7)
def offload(c):return rvv(c) or csr(c) and (c>>20)&4095 in (8,9,10,15,0xc20,0xc21,0xc22)
def memop(c):
    if c&3!=3:return compressed_memory(c)
    op,f=c&127,(c>>12)&7
    if op not in (3,35):return None
    imm=c>>20 if op==3 else ((c>>25)<<5)|((c>>7)&31)
    if imm&2048:imm-=4096
    return dict(kind='read' if op==3 else 'write',size=1<<(f&3),base=(c>>15)&31,
                register=(c>>(7 if op==3 else 20))&31,offset=imm)

def specification(elf,spike=False):
    s,_=disassemble(elf);fs=s['functions'];body=fs[NAME+'_main']
    routines=[fs['op_'+str(i)] for i in range(10)]
    require([len(r) for r in routines]==[16]*4+[21]*6,'Original helper lengths')
    require([r['insn'] for r in fs['capacity']]==['52fd','00b2f557','8082'],'Capacity512 code')
    def unique(enc):
        hits=[r for r in body if r['insn']==enc]
        require(len(hits)==1,'Unique compiled site '+enc);return hits[0]['pc']
    stores=[r for r in body if r['insn']=='00e78023']
    require(len(stores)==2,'Exact mask/output byte store sites')
    sites=dict(mask=stores[0]['pc'],output=stores[1]['pc'],a=unique('feb73c23'),b=unique('e214'),
               bits=unique('0006c583'),one=unique('00074603'),zero=unique('fc074783'),flags=unique('00e7db03'))
    for key,label in [('guard0','<output>'),('guard1','<output+0x41>')]:
        hit=[r for r in body if r['text'].startswith('lbu\t') and label in r['text']]
        require(len(hit)==1,'Exact guard site');sites[key]=hit[0]['pc']
    prel=[r for f in ('_start','main') for r in fs[f] if csr(int(r['insn'],16))]
    require(len(prel)==6 and [r['insn'] for r in prel[:5]]==['30401073','30529073','3002a073','00305073','00805073'],'Bootstrap CSR')
    exits=[r for r in fs['replay_exit'] if r['text'].startswith('sd\t')]
    require(len(exits)==1,'Single terminal store');exit_store=exits[0]
    park=[r for r in fs['replay_exit'] if r['pc']>exit_store['pc']]
    require(len(park)==1 and park[0]['insn']=='a001','Original park')
    return dict(**s,routines=routines,capacity=fs['capacity'],sites=sites,prelude=prel,spike=spike,
        exit_store=exit_store,park=park[0],exit_address=s['symbols']['tohost'] if spike else 0xd0000000)

def setup(s,g):
    a=s['symbols'];p=s['sites']
    for i,v in enumerate(g['mask']):yield p['mask'],a['mask']+i,v,1
    for i in range(0,CAP,4):
        for n in ('a','b'):
            yield p[n],a[n]+2*i,sum(g[n][i+j]<<(16*j) for j in range(4)),8
    for i in range(130):yield p['output'],a['output']+i,91,1

def packed(g,k):
    zero=sum((1 not in g['allowed'][k*8+b])<<b for b in range(8))
    one=sum((0 not in g['allowed'][k*8+b])<<b for b in range(8))
    return zero,one

def audit(rows,s,spike_vectors=False,abort=None):
    golds=model()['rows'];a=s['symbols'];sites=s['sites'];code=s['code']
    lookup={r['pc']:(op,i) for op,rr in enumerate(s['routines']) for i,r in enumerate(rr)}
    caplookup={r['pc']:i for i,r in enumerate(s['capacity'])}
    regs={0:0};vectors={};csrs={};fps={};counts=Counter();calls=[];offloads=[]
    step=capstep=prestep=pos=retired=parks=0;current=None;exited=False;lastcycle=-1
    events=list(setup(s,golds[0]));console=bytearray(8192);firmware_to_exit=None
    setpcs={sites[n] for n in ('mask','a','b','output')}
    readpcs={sites[n] for n in ('one','zero','bits','flags','guard0','guard1')}
    areas=[(a[n],a[n]+size) for n,size in [('a',2048),('b',2048),('mask',128),('output',130)]]
    def finish():
        if current is not None:
            require(step==0 and current['reads']==195,'Incomplete64 packed bytes/flags/guards')
            require(current['vstart']==0 and current['flags']==golds[len(calls)-1]['flags'],'Missing CSR oracle')
    for row in rows:
        if abort is not None and retired%4096==0:require(not abort.is_set(),'Sticky abort')
        require(not row.get('trap',0),'Unexpected trap')
        cycle=row.get('cycle',retired);require(cycle>=lastcycle,'Cycle reversal');lastcycle=cycle
        event=row.get('event','retire');require(event in EVENTS,'Exact six-event whitelist')
        if event!='retire':continue
        require(row.get('order',retired)==retired,'Retirement order')
        pc,c,rd,value=[row.get(k,0) for k in ('pc','insn','rd','value')]
        ins=code.get(f'{pc:x}');require(ins is not None and int(ins['insn'],16)==c,'Actual ELF PC/code')
        retired+=1
        address,rmask,wmask,wdata=[row.get(k,0) for k in ('address','rmask','wmask','wdata')]
        if exited:
            require(pc==s['park']['pc'] and not(rd or rmask or wmask),'Post-exit original park only')
            parks+=1;continue
        require(pc!=a['trap_entry'],'Trap entry')
        if step:require(pc==s['routines'][golds[len(calls)-1]['op']][step]['pc'],'Noncontiguous helper window')
        if 0<capstep<3:require(pc==s['capacity'][capstep]['pc'],'Noncontiguous capacity')
        pair=lookup.get(pc)
        if csr(c) and pair is None:
            require(prestep<6 and pc==s['prelude'][prestep]['pc'] and not calls and not capstep,'CSR outside bootstrap')
            if prestep<5:
                src=(c>>15)&31;operand=src if c&(1<<14) else regs.get(src)
                require(operand==[0,a['trap_entry'],0x6600,0,0][prestep] and rd==0,'Bootstrap CSR operand')
            else:require(value==128 and rd==(c>>7)&31,'vlenb128')
            if prestep==4:csrs['vstart']=0  # Exact observed csrwi vstart,0 above.
            prestep+=1
        if pc in caplookup:
            i=caplookup[pc];require(i==capstep and prestep==6 and not calls,'Capacity exactly once')
            if i==0:require((rd,value)==(5,(1<<64)-1),'Capacity AVL')
            if i==1:require((rd,value)==(10,CAP),'Capacity512')
            capstep+=1
        if rvv(c):require(pair is not None or pc==s['capacity'][1]['pc'],'RVV outside approved source windows')
        if pc in setpcs:
            require(capstep==3 and prestep==6 and step==0,'Setup phase')
            finish();require(pos<len(events),'Extra initialization')
            ep,ea,ev,width=events[pos]
            require((pc,address,wdata&((1<<(8*width))-1),wmask,rmask)==
                    (ep,ea,ev,((1<<width)-1)<<(ea%8),0),'Full original setup order/value/BE')
            d=memop(c)
            require(d and d['kind']=='write' and d['size']==width and d['register'] in regs and
                    (regs[d['register']]&((1<<(8*width))-1))==ev and d['base'] in regs and
                    ((regs[d['base']]+d['offset'])&((1<<64)-1))==ea,'Setup known source/base register')
            pos+=1
        elif wmask and not rvv(c):
            touches=any(address<hi and address+8>lo for lo,hi in areas)
            require(not touches or pc<a['trap_entry'] and not calls and pos==0 and wdata==0,'Unexpected write into original arrays')
            require(not(a['packed_cases']<=address<a['input_rows']+5120),'Write into immutable packed tables')
        if pair is not None:
            op,i=pair;require(i==step and capstep==3 and prestep==6,'Helper entry/order/phase')
            rr=s['routines'][op];delta=5 if op>=4 else 0
            if i==0:
                finish();j=len(calls);require(j<BOUND and pos==len(events),'Full setup/extra call')
                g=golds[j];require(op==g['op'],'Original operation order')
                args=[a['a'],a['b'],a['output']+1,g['vl'],CAP,a['mask'],0,g['sticky']]
                require([regs.get(n) for n in range(10,18)]==args,'Exact eight helper arguments')
                require((rd,value)==(30,0),'Save prior fflags0')
                current=dict(ordinal=j+1,op=op,vl=g['vl'],mode=g['mode'],sticky=g['sticky'],reads=0,vstart=None,flags=None)
                calls.append(current)
            g=golds[len(calls)-1]
            if i in (1,5+delta,13+delta):require((rd,value)==(5,g['vl'] if i==5+delta else CAP),'Original vset return')
            if spike_vectors and i in (2,3,4):
                required=range(8,16) if i==2 else range(16,24) if i==3 else [0]
                require(all(n in row.get('vectors',{}) for n in required),'Fresh per-call vector load payload')
            if op>=4:
                scalar=g['b'][0];boxed=scalar|0xffffffffffff0000
                if i==5:require((rd,value,address,rmask)==(7,scalar,a['b'],3<<(a['b']%8)),'Scalar half input')
                if i==6:require((rd,value)==(28,(1<<64)-1),'Boxing allones')
                if i==7:require((rd,value)==(28,0xffffffffffff0000),'Boxing upper48')
                if i==8:require((rd,value)==(7,boxed),'Boxed scalar bits')
                if i==9:
                    require(regs.get(7)==boxed,'fmv source')
                    if spike_vectors:require(row.get('fp',{}).get(0)==boxed,'Full scalar FP register payload')
            if i==6+delta:require(rd==0 and regs.get(17)==g['sticky'],'Set sticky flags')
            if i==7+delta:
                current['target']=dict(pc=hex(pc),encoding=ins['insn'],cycle=cycle,retired=retired)
                if spike_vectors:
                    require(csrs.get('vl')==g['vl'] and csrs.get('vtype')==11 and csrs.get('vstart')==0,'Actual target CSR')
                    for base,vals in ((8,g['a']),(16,g['b'])):
                        require(all(n in vectors for n in range(base,base+8)),'Full m8 source registers present')
                        actual=[(vectors[base+k//64]>>(16*(k%64)))&65535 for k in range(CAP)]
                        require(actual==vals,'Full original source VRF values')
                    require(vectors.get(0,-1)&((1<<512)-1)==int.from_bytes(bytes(g['mask'][:64]),'little'),'Actual predicate512 bits')
                    if op>=4:require(fps.get(0)==boxed,'Boxed FP target operand')
            if i==8+delta:require((rd,value)==(10,0),'Returned vstart');current['vstart']=value
            if i==9+delta:require((rd,value)==(6,g['flags']),'Actual fflags');current['flags']=value
            if i==10+delta:require((rd,value)==(6,g['flags']<<32),'Shift flags')
            if i==11+delta:require((rd,value)==(10,g['flags']<<32),'Packed status')
            if i==12+delta:require(rd==0 and regs.get(30)==0,'Restore prior fflags')
            if i==14+delta:
                require(regs.get(12)==a['output']+1,'Original mask store pointer')
                if spike_vectors:
                    accesses=row.get('accesses',[]);require(len(accesses)==64,'Full64-byte vector result store')
                    for k,(addr,v) in enumerate(accesses):
                        require(addr==a['output']+1+k and v is not None and 0<=v<=255,'Mask store byte/address')
                        require(all((v>>b)&1 in g['allowed'][k*8+b] for b in range(8)),'Full vector store oracle')
            counts[op,i]+=1;step=(step+1)%len(rr)
        if pc in readpcs:
            require(current is not None and step==0,'Oracle phase')
            k=current['reads'];require(k<195,'Extra oracle access')
            ordinal=len(calls)-1;record=a['packed_cases']+ordinal*144
            if k<192:
                byte,part=divmod(k,3);zero,one=packed(g,byte)
                key=('one','zero','bits')[part]
                addr=record+(80+byte if part==0 else 16+byte) if part<2 else a['output']+1+byte
                expected=one if part==0 else zero if part==1 else None;width=1
            else:
                key=('flags','guard0','guard1')[k-192]
                addr=record+14 if key=='flags' else a['output']+(0 if key=='guard0' else 65)
                width=2 if key=='flags' else 1;expected=g['flags'] if key=='flags' else 91
            require(pc==sites[key] and address==addr and rmask==((1<<width)-1)<<(addr%8) and
                    not wmask and rd==(c>>7)&31,'Exact packed oracle PC/address/order/width')
            d=memop(c);require(d and d['base'] in regs and (regs[d['base']]+d['offset'])&((1<<64)-1)==addr,'Oracle base register')
            if expected is None:
                require(0<=value<=255 and all((value>>b)&1 in g['allowed'][byte*8+b] for b in range(8)),'All original result bits')
            else:require(value==expected,'Original packed mask/flag/guard value')
            current['reads']+=1
            if current['reads']==195:
                events=list(setup(s,golds[len(calls)])) if len(calls)<BOUND else [];pos=0
        elif rmask and a['output']<=address<a['output']+130:
            require(pair is not None,'Unexpected output load')
        if offload(c):
            backend=rvv(c) and not(c&127==87 and (c>>12)&7==7)
            if pair is not None and pair[1]==7+(5 if pair[0]>=4 else 0):backend=backend and g['vl']>0
            offloads.append(dict(pc=pc,insn=c,backend_required=bool(backend)))
        vectors.update(row.get('vectors',{}));csrs.update(row.get('csrs',{}));fps.update(row.get('fp',{}))
        if spike_vectors and pair is not None and pair[1]==7+(5 if pair[0]>=4 else 0):
            require(8 in vectors and all((vectors[8]>>k)&1 in g['allowed'][k] for k in range(CAP)),'Full reference result vector')
        if s['spike'] and wmask and a['replay_log']<=address<a['replay_log']+8192:
            console[address-a['replay_log']]=wdata&255
        if pc==s['exit_store']['pc'] or address==s['exit_address'] and wmask:
            require(pc==s['exit_store']['pc'] and address==s['exit_address'] and wmask==255 and wdata==int(s['spike']),'Actual exit0')
            finish();require(len(calls)==BOUND,'Incomplete682');exited=True;firmware_to_exit=retired
        if rd:regs[rd]=value
    finish();require(exited and prestep==6 and capstep==3 and len(calls)==BOUND,'Complete scope/exit')
    multiplicities=Counter(g['op'] for g in golds)
    require(all(counts[op,i]==multiplicities[op] for op in range(10) for i in range(len(s['routines'][op]))),'Every original helper instruction count')
    return dict(status='FULL_ORIGINAL682_STRICT_ACCEPTED_NOT_FULL_PARENT',target_calls=BOUND,
        full_result_bit_checks=BOUND*CAP,result_bytes=BOUND*64,guard_checks=BOUND*2,
        returned_vstart_zero=BOUND,returned_flags_checked=BOUND,helper_instructions=sum(counts.values()),
        firmware_retired_to_exit=firmware_to_exit,retired=retired,park_retired=parks,calls=calls,
        full_reference_vectors=spike_vectors,retired_offloads=offloads,reconstructed_console=console.split(b'\0',1)[0].decode('ascii'))

def spike_rows(path):
    pattern=re.compile(r'core\s+0:\s+\d\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)')
    boot=[(0x1000,0x297),(0x1004,0x02028593),(0x1008,0xf1402573),(0x100c,0x0182b283),(0x1010,0x28067)]
    nboot=0
    with path.open() as stream:
        for number,line in enumerate(stream,1):
            require('trap_' not in line,'Spike trap');m=pattern.fullmatch(line.strip());require(m is not None,'Unparsed raw record '+str(number))
            pc,c,rest=int(m[1],16),int(m[2],16),m[3]
            if pc<0x80000000:
                require(nboot<5 and (pc,c)==boot[nboot],'Reset ROM');nboot+=1;continue
            require(nboot==5,'Missing reset ROM')
            rd=re.search(r'\bx\s*(\d+)\s+0x([0-9a-f]+)',rest)
            accesses=[(int(x,16),int(v,16) if v else None) for x,v in re.findall(r'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?',rest)]
            address=rmask=wmask=wdata=0;d=memop(c)
            if d and accesses:
                require(len(accesses)==1,'Single scalar memory effect')
                address,val=accesses[0];width=d['size']
                if val is None:rmask=((1<<width)-1)<<(address%8)
                else:wmask=((1<<width)-1)<<(address%8);wdata=val
            yield dict(pc=pc,insn=c,rd=int(rd[1]) if rd else 0,value=int(rd[2],16) if rd else 0,address=address,
                rmask=rmask,wmask=wmask,wdata=wdata,accesses=accesses,
                vectors={int(n):int(v,16) for n,v in re.findall(r'\bv\s*(\d+)\s+0x([0-9a-f]+)',rest)},
                fp={int(n):int(v,16) for n,v in re.findall(r'\bf\s*(\d+)\s+0x([0-9a-f]+)',rest)},
                csrs={n:int(v,16) for n,v in re.findall(r'\bc\d+_(vl|vtype|vstart)\s+0x([0-9a-f]+)',rest)})
