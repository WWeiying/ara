"""Successor: include the original wrapper retry VSET in strict RVV ownership."""
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOT = HERE.parent.parent / 'negative_stride_load_original01/observer.py'
spec = importlib.util.spec_from_file_location('ns_pilot_utilities', PILOT)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
require, readint = old.require, old.readint
disassemble, window, elf_bytes = old.disassemble, old.window, old.elf_bytes
G, VA, U64 = old.G, old.VA, old.MASK64
DONE = 0x6e65677376333938
STATUS_MASK = 0x8000031888 | 0xc0000


def geom(t):
    stride = -(1+t['gap'])*2
    base = 4096-t['boundary']*stride-2
    mask = {2:0x24, 3:0}[t['mode']]
    active = [i for i in range(8) if mask>>i & 1]
    start = next((i for i in active if base+i*stride < 4096), 8)
    return dict(stride=stride, base=base, mask=mask, active=active, start=start,
                fault=start<8, prefix=[i for i in active if i<start] if start<8 else [])


def orig(h): return (37*h+11)&65535


def vector(t, phase, r, i):
    g=geom(t)
    if r!=1: return 0x6c00+256*r+i
    if t['store']: return 101+13*i
    if phase and i in g['active'] and (phase==3 or i<g['start']):
        return orig((g['base']+i*g['stride'])//2)
    return 91


def data(t, phase, h):
    g=geom(t); value=orig(h)
    i=next((i for i in range(8) if g['base']+i*g['stride']==2*h), None)
    if phase and i in g['active']:
        if t['store'] and (i<g['start'] or phase==3): value=101+13*i
        if phase>=2 and i in g['prefix']: value^=91
    return value


def pending(t,phase,h):
    g=geom(t)
    return bool(t['store'] and g['fault'] and
                (phase==1 or (phase==2 and not t['unmapped'])) and
                any(g['base']+i*g['stride']==2*h for i in g['active'] if i>=g['start']))


def host_check(path, cases):
    want=[]
    for c,t in enumerate(cases):
        for p in range(4):
            want.extend(f'V {c} {p} {r} {i} {vector(t,p,r,i)}' for r in range(3) for i in range(64))
            want.extend(f'D {c} {p} {h} {data(t,p,h)} {int(pending(t,p,h))}' for h in range(4096))
    require(Path(path).read_text().splitlines()==want,'C/independent phase oracle')
    return len(want)


def expected(s,t,phase,case):
    g=geom(t); m={}; p=s['mx_pages']; pte=lambda a,f:(a>>12<<10)|f
    protected=0 if t['unmapped'] else pte(p,0xc9)
    def put(a,v,n=8):
        values=[None]*n if v is None else v.to_bytes(n,'little')
        for i,b in enumerate(values):
            require(a+i not in m,'Overlapping expected fields');m[a+i]=b
    require(p%4096==0 and s['mx_guard_lo']==p-64 and s['mx_guard_hi']==p+20480,'Physical guards')
    for h in range(4096): put(p+2*h,None if pending(t,phase,h) else data(t,phase,h),2)
    entries={1:pte(p+12288,1),2:0x200000cf,512:pte(p+16384,1),1024:pte(p,0xc7) if phase>=2 else protected,1025:pte(p+4096,0xc7)}
    for i in range(1536):put(p+8192+8*i,entries.get(i,0))
    for name in ('mx_guard_lo','mx_guard_hi'):
        for i in range(8):put(s[name]+8*i,G)
    final=phase==3 or (not g['fault'] and phase>=1)
    for name in ('mx_seed','mx_fault','mx_result'):
        for i in range(8):put(s[name]+8*i,G);put(s[name]+448+8*i,G)
        live=name=='mx_seed' or (name=='mx_fault' and g['fault'] and phase>=1) or (name=='mx_result' and final)
        vp=0 if name=='mx_seed' else 1 if name=='mx_fault' else 3
        for r in range(3):
            for i in range(64):
                val=vector(t,vp,r,i) if live else (G>>(16*(i%4)))&65535
                if live and name=='mx_fault' and not t['store'] and r==1 and i in g['active'] and i>=g['start']:
                    val=None
                put(s[name]+64+128*r+2*i,val,2)
    for i in range(128):
        put(s['mx_input']+2*i,101+13*i if i<64 else 0,2)
        b=t['boundary'];slot=(i+1)%b if i<b else b+(i-b+1)%(8-b) if i<8 else i
        put(s['mx_offsets']+2*i,2*slot,2)
    for i in range(130):put(s['mx_out']+2*i,vector(t,3,1,i-1) if final and 1<=i<=64 else 91,2)
    for i in range(16):put(s['mx_mask']+i,g['mask'],1)
    satp=(8<<60)|((p+8192)>>12)
    for name,val in dict(mx_case=case,mx_stride=g['stride']&U64,mx_base=VA+g['base'],mx_store=t['store'],mx_satp=satp,
                         mx_count=(1+g['fault'] if final else 1 if phase else 0),mx_marker=int(final),
                         mx_restart=g['start'] if g['fault'] and phase else 0,mx_return=0,mx_errors=0,mx_unexpected=0,
                         mx_phase=phase,mx_cases_done=case).items():put(s[name],val)
    for i in range(8):put(s['mx_prefix']+8*i,101+13*i if t['store'] and phase and i in g['prefix'] else U64)
    for j,v in enumerate([64,8,0,117,5,0]):put(s['mx_post']+8*j,v if final else U64)
    for n in range(2):
        fault_record=g['fault'] and n==0
        live=phase>=1 if fault_record else final and n==int(g['fault'])
        row=[15 if t['store'] else 13,s[f'fault_{t["store"]}_pc'],VA+g['base']+g['start']*g['stride'],0x800,satp,8,8,g['start'],117,5,0,protected]
        if not fault_record:row=[9,s['mx_ecall'],0,0x800,satp,64,8,0,117,5,1,pte(p,0xc7) if g['fault'] else protected]
        for j,v in enumerate(row):
            if live and j==3:continue
            put(s['mx_records']+96*n+8*j,v if live else U64)
    return m


def compare(mem,s,t,phase,case):
    gold=expected(s,t,phase,case)
    for a,v in gold.items():
        require(a in mem and (v is None or mem[a]==v),f'case{case} phase{phase} byte {a:x}: {mem.get(a)} != {v}')
    g=geom(t);n=1+g['fault'] if phase==3 or (phase and not g['fault']) else int(phase>0)
    for i in range(n):require(readint(mem,s['mx_records']+96*i+24)&STATUS_MASK==0x800,'Trap status/MXR/SUM')
    return dict(bytes=len(gold),unconstrained_partial_bytes=sum(v is None for v in gold.values()))


def check_counts(cases):
    total=3; points={}
    for c,t in enumerate(cases):
        g=geom(t);total+=1+4113;points[c,0]=total
        if g['fault']:
            unfinished=len([i for i in g['active'] if i>=g['start']])
            total+=12+(len(g['prefix']) if t['store'] else 0)+208-(0 if t['store'] else unfinished)
            total+=4113-(unfinished if t['store'] else 0);points[c,1]=total
            total+=4113-(unfinished if t['store'] and not t['unmapped'] else 0);points[c,2]=total
            total+=12+364
        else:
            total+=12+364+4113;points[c,1]=total
            total+=4113;points[c,2]=total
        total+=4113;points[c,3]=total
        total+=208
    return points,total+15


def expected_actions(t):
    g=geom(t)
    repair=['repair_sfence']+(['refill'] if t['unmapped'] else [])+['checkpoint2']
    if g['fault']:
        return ['checkpoint0','fault','checkpoint1']+repair+['retry_mret','target','younger','ecall','checkpoint3']
    return ['checkpoint0','target','younger','ecall','checkpoint1']+repair+['checkpoint3']


def retry_context(s,t,regs,csr):
    g=geom(t)
    require(csr.get(0x341)==s[f'fault_{t["store"]}_pc'] and csr.get(8)==g['start'],'Retry PC/start')
    require(csr.get(0xc20)==8 and csr.get(0xc21)==8 and csr.get(0x300,0)&0x1800==0x800,'Retry VL/type/privilege')
    require([regs.get(i) for i in range(10,16)]==[VA+g['base'],s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']]
            and regs.get(28)==g['stride']&U64,'Original retry arguments/stride')


def analyze(path,s,code,elf,cases,limit):
    mem,regs,csr=elf_bytes(elf),{0:0},{}
    points,final_checks=check_counts(cases)
    summaries=[dict(actions=[],helpers=[],targets=[],traps=[],mrets=[],checkpoints=[],capacity=0,entry=0) for _ in cases]
    helpers={i:window(code,s[f'replay_{i}'],10) for i in (0,1)}
    geometries=[geom(t) for t in cases]
    def rvv(insn):return insn&127==0x57 or (insn&127 in (7,39) and (insn>>12)&7 in (0,5,6,7))
    vector_pcs={pc for pc,insn in code.items() if rvv(insn)}
    snapshot_pcs={pc for pc in vector_pcs if s['mx_snapshot']<=pc<s['mx_handler']}
    entry_pcs={pc for pc in vector_pcs if s['mx_s_entry']<=pc<s['mx_call_store']}
    restore_pcs={pc for pc in vector_pcs if code[pc]&0xfe007fff==0x80007057}
    retry_pcs={pc for pc in vector_pcs if s['mx_handler']<=pc<s['mx_return_m']}
    known=set().union(*map(set,helpers.values()),set(window(code,s['capacity'],3)),snapshot_pcs,entry_pcs,restore_pcs,retry_pcs)
    require(vector_pcs<=known and len(snapshot_pcs)==4 and len(entry_pcs)==3 and len(restore_pcs)==1 and len(retry_pcs)==1,'Static RVV ownership')
    require(all(code[pc]==0x0082f2d7 for pc in retry_pcs),'Exact archived wrapper retry vset encoding')
    vector_counts={pc:0 for pc in vector_pcs}
    capacity=window(code,s['capacity'],3);cap_seen=[]
    n=fw=boot=parks=checks=0;exits=[];saved={};restored=False;last_dis=None
    rx=re.compile(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')
    for line in Path(path).open():
        match=rx.match(line)
        if not match:
            d=re.match(r'^core\s+0:\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)',line)
            if d:last_dis=(int(d[1],16),int(d[2],16))
            trap=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
            if trap:
                c=readint(mem,s['mx_case']);require(c<len(cases),'Exception outside cases')
                t=cases[c];g=geom(t);item=summaries[c];epc=int(trap[2],16)
                target=s[f'fault_{t["store"]}_pc']
                if trap[1]=='trap_supervisor_ecall':
                    require(epc==s['mx_ecall'],'Wrong ecall PC');item['actions'].append('ecall')
                else:
                    require(g['fault'] and trap[1]==('trap_store_page_fault' if t['store'] else 'trap_load_page_fault') and epc==target,'Unexpected architectural exception')
                    require(last_dis==(target,code[target]),'Fault instruction/code evidence')
                    item['actions'].append('fault')
                item['traps'].append(dict(cause=trap[1],pc=hex(epc),firmware_records=fw))
            continue
        mode,pc,insn,tail=int(match[1]),int(match[2],16),int(match[3],16),match[4];n+=1
        if pc<0x80000000:
            require(not fw,'Late boot record');boot+=1;continue
        if exits:
            require(pc==s['_start']+0x7e and insn==0xa001 and not tail.strip(),'Post-HTIF side effect/not original park')
            parks+=1;continue
        fw+=1
        require(pc in code and code[pc]==insn,f'Actual PC/code {pc:x}/{insn:x}')
        require(pc!=s['trap_entry'],'Unexpected runtime trap')
        if pc in vector_counts:vector_counts[pc]+=1
        if pc in retry_pcs:
            ci=readint(mem,s['mx_case'])
            require(ci<len(cases) and geometries[ci]['fault'] and mode==3 and regs.get(5)==8 and
                    readint(mem,s['mx_phase'])==2 and readint(mem,s['mx_marker'])==0,
                    'Retry vset outside repaired fault window')
        updates={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        accesses=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        c=readint(mem,s['mx_case']) if all(s['mx_case']+j in mem for j in range(8)) else 0
        if pc==s['main']:saved=dict(csr)
        item=summaries[c] if c<len(cases) else None
        t=cases[c] if c<len(cases) else None;g=geometries[c] if t else None
        if pc in capacity:
            require(item is not None,'Capacity outside cases');cap_seen.append((c,pc))
            if pc==capacity[0]:item['capacity']+=1
        if any(pc in win for win in helpers.values()):
            require(item is not None and mode==1 and pc in helpers[t['store']],'Wrong helper/interior/privilege')
            item['helpers'].append(pc)
            if pc==helpers[t['store']][0]:
                item['entry']+=1
                require([regs.get(i) for i in range(10,16)]==[VA+g['base'],s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']],'Helper original arguments')
            if pc==s[f'fault_{t["store"]}_pc']:
                retry=bool(item['mrets'])
                require(regs.get(10)==VA+g['base'] and regs.get(28)==g['stride']&U64,'Target base/stride')
                require(csr.get(0xc20)==8 and csr.get(0xc21)==8 and csr.get(8)==(g['start'] if retry else 0),'Target CSR context')
                indices=g['prefix'] if g['fault'] and not retry else [i for i in g['active'] if not retry or i>=g['start']]
                want=[(VA+g['base']+i*g['stride'],101+13*i if t['store'] else None) for i in indices]
                require(accesses==want,'Actual target access addresses/values')
                item['targets'].append(dict(pc=hex(pc),vstart=csr[8],partial_fault_record=g['fault'] and not retry,
                    accesses=[[hex(a),v] for a,v in accesses],firmware_records=fw))
                if not g['fault'] or retry:item['actions'].append('target')
        if pc==s['mx_checkpoint']:
            phase=readint(mem,s['mx_phase']);require(item is not None,'Checkpoint case')
            count=compare(mem,s,t,phase,c)
            require(checks==readint(mem,s['mx_checks'])==points[c,phase],'Independent scalar checkpoint count')
            item['checkpoints'].append(dict(phase=phase,checks=checks,firmware_records=fw,**count));item['actions'].append('checkpoint'+str(phase))
        if pc==s['mx_repair_sfence']:
            require(item is not None and mode==3 and regs.get((insn>>15)&31)==VA,'Repair SFENCE address/mode');item['actions'].append('repair_sfence')
        if pc==s['mx_refill_page']:
            require(item is not None and t['unmapped'],'u0 unexpected refill');item['actions'].append('refill')
        if pc==s['mx_trap_mret'] and readint(mem,s['mx_marker'])==0:
            require(item is not None and g['fault'],'Unexpected retry')
            retry_context(s,t,regs,csr)
            item['mrets'].append(dict(mepc=hex(csr[0x341]),vstart=csr[8],arguments=[hex(regs[i]) for i in range(10,16)],stride=hex(regs[28])))
            item['actions'].append('retry_mret')
        if pc==s['mx_younger_store']:
            require(item is not None and mode==1,'Younger store mode');item['actions'].append('younger')
        if pc==s['check']:
            require(regs.get(10)==regs.get(11),f'Scalar mismatch case{c} check{checks+1}: {regs.get(10)} != {regs.get(11)}')
            checks+=1
        for a,v in accesses:
            if v is None:continue
            if insn&3!=3:
                d=old.decoder.decode(insn);require(d and d['kind']=='write','Compressed store decode');width=d['size']
                require(a==(regs.get(d['base'],-1)+d['offset'])&U64,'Compressed store address')
            elif insn&127==0x23:
                width=1<<((insn>>12)&7);imm=((insn>>25)<<5)|((insn>>7)&31);imm=imm-4096 if imm&2048 else imm
                require(a==(regs.get((insn>>15)&31,-1)+imm)&U64,'Scalar store address')
            else:
                require(insn&127==0x27,'Unknown write');width={0:1,5:2,6:4,7:8}[(insn>>12)&7]
            dest=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for j,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):mem[dest+j]=b
            if a==s['tohost']:exits.append(v)
        regs.update(updates);regs[0]=0
        csr.update({int(k):int(v,16) for k,v in re.findall(r'\bc([0-9]+)_[^\s]+\s+0x([0-9a-f]+)',tail)})
        if insn&127==0x73 and (insn>>12)&7==2 and (insn>>15)&31==0 and (insn>>7)&31 in updates:
            csr[insn>>20]=updates[(insn>>7)&31]
        if any(a==s['mx_completed'] for a,v in accesses):
            for k in (0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3):
                if k in saved:require(csr.get(k)==saved[k],f'Restored CSR{k:x}')
            restored=True
    for c,t in enumerate(cases):
        item=summaries[c];g=geom(t);win=helpers[t['store']]
        require(item['actions']==expected_actions(t),f'case{c} action order {item["actions"]}')
        require(item['capacity']==item['entry']==1,'Capacity/helper multiplicity')
        # Spike may omit an entirely side-effect-free faulting target record.
        choices=[win[:5]+win[5:],win[:6]+win[5:]] if g['fault'] else [win]
        require(item['helpers'] in choices,'Exact helper interior/retry order')
        require(len(item['mrets'])==int(g['fault']) and len(item['traps'])==1+int(g['fault']),'Trap/retry counts')
        require([p['phase'] for p in item['checkpoints']]==[0,1,2,3],'All checkpoints')
        require([(cc,pc) for cc,pc in cap_seen if cc==c]==[(c,pc) for pc in capacity],'Capacity full code')
        item['helper_retirements']=len(item.pop('helpers'))
    for pc in snapshot_pcs:require(vector_counts[pc]==sum(1+g['fault'] for g in geometries),'Snapshot RVV count')
    for pc in entry_pcs:require(vector_counts[pc]==len(cases),'Entry RVV count')
    for pc in restore_pcs:require(vector_counts[pc]==1,'Extra restore/vector operation')
    for pc in retry_pcs:require(vector_counts[pc]==sum(g['fault'] for g in geometries),'Retry vset exact count')
    require(exits==[1] and readint(mem,s['mx_completed'])==DONE and readint(mem,s['mx_errors'])==readint(mem,s['mx_unexpected'])==0,'Actual HTIF/completion/errors')
    require(readint(mem,s['mx_cases_done'])==len(cases) and checks==readint(mem,s['mx_checks'])==final_checks,'Full group/counts')
    require(restored and fw<limit and boot==5,'CSR/firmware/boot bound')
    return dict(status='REFERENCE_PASS_NOT_DUT',case_count=len(cases),cases=summaries,
        scalar_checks=checks,firmware_records_through_htif=fw,commit_records=n,boot_records=boot,park_records=parks,
        htif=exits,vector_pc_counts={hex(p):v for p,v in vector_counts.items()},output_elements_per_case=64,output_guards_per_case=2,full_memory_bytes_per_case=8192,
        original_linux_equivalence=False,parent96_closed=False)

