"""Original sixteen-case oracle; independent byte model and full Spike events."""
import importlib.util
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'negative_stride_store_original01/observer.py'
spec=importlib.util.spec_from_file_location('zero_stride_memory_base',BASE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
require=base.require
readint=base.readint
disassemble=base.disassemble
window=base.window
DECODER=base.DECODER
VA=0x40000000
G=0xe370697ce370697c
MASK64=(1<<64)-1
DONE=0x7a65726f31360001
LIMIT=8000000

def config(c):
    require(c in range(16),'Case outside original16')
    return c//8,(c//4)%2,c%4

def active(c,i):return i<8 and bool(((255,170,36,0)[c%4]>>i)&1)
def vector(c,i):return 101 if (c//4)%2 else 18955 if active(c,i) else 91
def data(c,p,i):return 101 if p>=3 and (c//4)%2 and c%4<3 and i==512 else 37*i+11

def expected(s,c,p):
    require(p in range(5),'Unknown checkpoint')
    u,store,mode=config(c);fault=mode<3
    m={}
    def put(a,v,n=8):
        for i,b in enumerate(v.to_bytes(n,'little')):
            require(a+i not in m,'Overlapping oracle');m[a+i]=b
    pages=s['mx_pages'];pte=lambda a,f:(a>>12<<10)|f
    require(pages%4096==0 and s['mx_guard_lo']==pages-64 and s['mx_guard_hi']==pages+20480,'Page allocation/guards')
    for i in range(1024):put(pages+8*i,data(c,p,i))
    repaired=p==4 or (fault and p>=2)
    upper=pte(pages+4096,0xc7) if repaired else 0 if u else pte(pages+4096,1)
    entries={1:pte(pages+12288,1),2:0x200000cf,512:pte(pages+16384,1),1024:pte(pages,0xc7),1025:upper}
    for i in range(1536):put(pages+8192+8*i,entries.get(i,0))
    for name in ('mx_guard_lo','mx_guard_hi'):
        for i in range(8):put(s[name]+8*i,G)
    for i in range(512):
        put(s['mx_input']+8*i,101 if i<64 else 0)
        put(s['mx_offsets']+8*i,8*((i+1)%8 if i<8 else i))
    for i in range(514):put(s['mx_out']+8*i,vector(c,i-1) if p>=3 and 1<=i<=64 else 91)
    for i in range(64):put(s['mx_mask']+i,(255,170,36,0)[mode],1)
    for name in ('mx_fault','mx_result'):
        for i in range(8):put(s[name]+8*i,G);put(s[name]+576+8*i,G)
        live=(name=='mx_fault' and fault and p>=1) or (name=='mx_result' and p>=3)
        for i in range(64):
            if name=='mx_fault' and live and i>=mode:continue
            value=(101 if store else 91) if name=='mx_fault' else vector(c,i)
            put(s[name]+64+8*i,value if live else G)
    satp=(8<<60)|((pages+8192)>>12)
    scalar={'mx_case':c,'mx_phase':p,'mx_store':store,'mx_unmapped':u,'mx_mode':mode,
            'mx_stride':0,'mx_satp':satp,'mx_count':(2 if fault else 1) if p>=3 else int(fault and p>=1),
            'mx_marker':int(p>=3),'mx_restart':mode if fault and p>=1 else 0,
            'mx_return':0,'mx_errors':0,'mx_unexpected':0,
            'mx_signals':sum(j%4<3 for j in range(c))+int(fault and p>=1)}
    for name,v in scalar.items():put(s[name],v)
    for name in ('mx_action_source','mx_action_copy'):
        for i,v in enumerate((s['mx_handler'],4,0)):put(s[name]+8*i,v)
    for row in range(16):
        ru,rs,rm=config(row);rf=rm<3
        done=row<c or row==c and p>=3
        fseen=rf and (row<c or row==c and p>=1)
        for j,v in enumerate((64,26,0,0,0,0)):put(s['mx_post']+48*row+8*j,v if done else MASK64)
        for n in range(2):
            isfault=rf and n==0
            live=fseen if isfault else done and n==int(rf)
            values=[15 if rs else 13,s['fault_1_pc'] if rs else s['fault_0_pc'],VA+4096,
                    0x800,satp,8,26,rm,0,0,0,0 if ru else pte(pages+4096,1)] if isfault else [
                    9,s['mx_ecall'],0,0x800,satp,64,26,0,0,0,1,
                    pte(pages+4096,0xc7) if rf else 0 if ru else pte(pages+4096,1)]
            for j,v in enumerate(values):
                if live and j==3:continue
                put(s['mx_records']+row*192+n*96+8*j,v if live else MASK64)
    return m

def compare(memory,s,c,p):
    gold=expected(s,c,p)
    for a,v in gold.items():
        require(memory.get(a)==v,f'Case{c} phase{p} byte{a:x} expected{v:02x} actual{memory.get(a)}')
    for row in range(c+1):
        count=(2 if row%4<3 else 1) if row<c or p>=3 else int(row%4<3 and p>=1)
        for n in range(count):require(readint(memory,s['mx_records']+row*192+n*96+24)&0x8000031888==0x800,'Trap status')
    return len(gold)

def host_check(text):
    lines=[]
    for c in range(16):
        u,st,m=config(c);lines.append(f'C {c} {u} {st} {(255,170,36,0)[m]} {m if m<3 else 8}')
        lines.extend(f'V {c} {i} {vector(c,i)}' for i in range(64))
        lines.extend(f'D {c} {i} {data(c,4,i)}' for i in range(1024))
    require(text.splitlines()==lines,'Independent Host full-original oracle mismatch')
    return len(lines)

def args(s):return [VA+4096,s['mx_input'],s['mx_out']+8,s['mx_mask'],64,s['mx_stride']]

def analyze(path,s,code,elf):
    memory,regs,csr=base.elf_bytes(elf),{0:0},{}
    n=fw=checks=capacities=bootstraps=0
    points=[];traps=[];events=[];entries=[];mrets=[];refills=[];exits=[];helpers={c:[] for c in range(16)}
    helperpcs={j:window(code,s[f'replay_{j}'],10) for j in (0,1)}
    allhelper=set(helperpcs[0]+helperpcs[1]);saved={};restored=False
    case=-1;attempt=0
    for line in Path(path).open():
        trap=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
        if trap:traps.append((trap[1],int(trap[2],16)))
        match=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not match:continue
        mode,pc,insn,tail=int(match[1]),int(match[2],16),int(match[3],16),match[4];n+=1
        if pc<0x80000000:continue
        fw+=1;require(fw<=LIMIT,'Reference instruction ceiling')
        require(pc in code and code[pc]==insn,f'PC/code mismatch {pc:x}/{insn:x}')
        require(pc!=s['trap_entry'],'Unexpected runtime trap')
        updates={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        access=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc==s['main']:saved=dict(csr)
        if pc==s['capacity']:capacities+=1
        if pc==s['mx_bootstrap']:bootstraps+=1
        if pc in (s['replay_0'],s['replay_1']):
            case=readint(memory,s['mx_case']);attempt=0
            require(case==len(entries),'Not continuous original case order')
            require(pc==s[f'replay_{(case//4)%2}'] and mode==1,'Wrong helper/privilege')
            require([regs.get(i) for i in range(10,16)]==args(s),'Original helper arguments')
            entries.append(case)
        if pc in allhelper:
            require(case in range(16) and mode==1 and pc in helperpcs[(case//4)%2],'Wrong helper execution')
            helpers[case].append(pc)
        if pc in (s['fault_0_pc'],s['fault_1_pc']):
            u,st,mask=config(case);fault=mask<3 and attempt==0
            require(pc==s[f'fault_{st}_pc'] and regs.get(28)==0 and regs.get(10)==VA+4096,'Target/base/zero stride')
            require([csr.get(k) for k in (0xc20,0xc21,8)]==[8,26,mask if attempt else 0],'Target VL/type/start')
            expected=[] if fault else [(VA+4096,101 if st else None) for i in range(8) if active(case,i)]
            require(access==expected,f'Case{case} attempt{attempt} active target accesses {access}')
            events.append(dict(case=case,attempt=attempt,vstart=csr[8],pc=hex(pc),commit=fw,accesses=access));attempt+=1
        if pc==s['mx_checkpoint']:
            c=readint(memory,s['mx_case']);p=readint(memory,s['mx_phase'])
            points.append(dict(case=c,phase=p,bytes=compare(memory,s,c,p),commit=fw))
        if pc==s['mx_refill_page']:refills.append(readint(memory,s['mx_case']))
        if pc==s['mx_trap_mret'] and readint(memory,s['mx_marker'])==0:
            c=readint(memory,s['mx_case']);st=(c//4)%2
            require([regs.get(i) for i in range(10,16)]==args(s) and regs.get(28)==0,'Retry arguments changed')
            require(csr.get(0x341)==s[f'fault_{st}_pc'] and [csr.get(k) for k in (0xc20,0xc21,8)]==[8,26,c%4],'Retry PC/vector context')
            require(csr.get(0x300,0)&0x1800==0x800,'Retry privilege')
            mrets.append(dict(case=c,commit=fw,pc=hex(csr[0x341]),vstart=csr[8],base=hex(regs[10]),stride=regs[28]))
        if pc==s['check']:
            require(regs.get(10)==regs.get(11),f'Scalar oracle failure case{case} got{regs.get(10)} wanted{regs.get(11)}');checks+=1
        for a,v in access:
            if v is None:continue
            if insn&3!=3:
                d=base.decoder.decode(insn);require(d and d['kind']=='write','Unknown compressed store');width=d['size']
                require(a==(regs.get(d['base'],-1)+d['offset'])&MASK64,'Compressed write address')
            elif insn&127==0x23:
                width=1<<((insn>>12)&7);imm=((insn>>25)<<5)|((insn>>7)&31);imm=imm-4096 if imm&2048 else imm
                require(a==(regs.get((insn>>15)&31,-1)+imm)&MASK64,'Scalar write address')
            else:
                require(insn&127==0x27,'Unknown store');width={0:1,5:2,6:4,7:8}[(insn>>12)&7]
            pa=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):memory[pa+i]=b
            if a==s['tohost']:exits.append(v)
        regs.update(updates);regs[0]=0
        csr.update({int(k):int(v,16) for k,v in re.findall(r'\bc([0-9]+)_[^\s]+\s+0x([0-9a-f]+)',tail)})
        if insn&127==0x73 and (insn>>12)&7==2 and (insn>>15)&31==0 and (insn>>7)&31 in updates:
            csr[insn>>20]=updates[(insn>>7)&31]
        if any(a==s['mx_completed'] for a,v in access):
            for k in (0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3):
                if k in saved:require(csr.get(k)==saved[k],f'Final CSR restore {k:x}')
            restored=True
    wantpoints=[(c,p) for c in range(16) for p in ([0,1,2,3,4] if c%4<3 else [0,3,4])]
    require([(p['case'],p['phase']) for p in points]==wantpoints,'Missing/out-of-order checkpoints')
    wanttraps=[]
    for c in range(16):
        st=(c//4)%2;w=helperpcs[st]
        if c%4<3:wanttraps.append(('trap_store_page_fault' if st else 'trap_load_page_fault',s[f'fault_{st}_pc']))
        wanttraps.append(('trap_supervisor_ecall',s['mx_ecall']))
        require(helpers[c]==(w[:6]+w[5:] if c%4<3 else w),f'Case{c} original helper continuity/retry')
    require(traps==wanttraps,'Fault/ecall ledger differs')
    require(entries==list(range(16)) and capacities==1 and bootstraps==1,'Program/capacity/bootstrap multiplicity')
    require(refills==list(range(8,16)),'Original unmapped refill (including alloff) differs')
    require([r['case'] for r in mrets]==[c for c in range(16) if c%4<3],'Retry ledger')
    require(exits==[1] and readint(memory,s['mx_completed'])==DONE and restored,'Exit/completion/restore')
    require(readint(memory,s['mx_errors'])==readint(memory,s['mx_unexpected'])==0,'Error counters')
    require(readint(memory,s['mx_checks'])==checks and checks>=16*(64+1024+2),'Incomplete scalar oracle')
    require(readint(memory,s['mx_signals'])==12 and len(events)==28,'Signals/target attempts')
    return dict(status='REFERENCE_CHECKER_PASS_NOT_DUT',commits=n,firmware_commits=fw,scalar_checks=checks,
                checkpoints=points,targets=events,retry_mrets=mrets,traps=traps,refills=refills,
                cases=16,helper_entries=16,helper_instructions=172,capacity_calls=capacities,bootstrap_calls=bootstraps,
                output_elements=1024,output_guards=32,memory_words=16384,returned_vstart=16,faults=12,
                htif=exits,continuous=True,linux_signal_equivalence=False,historical_linux_stall_closed=False)
