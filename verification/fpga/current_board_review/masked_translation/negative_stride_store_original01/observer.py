"""Independent byte-address oracle and full retired-code Spike observer."""
import importlib.util
import re
import struct
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
DECODER=ROOT/'verification/coverage/scoped_rv64c_memory.py'
_spec=importlib.util.spec_from_file_location('negative_compressed_memory',DECODER)
decoder=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(decoder)
G=0xe370697ce370697c
VA=0x40000000
DONE=0x6e65677376333902
MASK64=(1<<64)-1

def require(ok,message):
    if not ok: raise ValueError(message)

def readint(memory,address,n=8):
    require(all(address+i in memory for i in range(n)),f'Missing bytes at {address:x}/{n}')
    return int.from_bytes(bytes(memory[address+i] for i in range(n)),'little')

def original(h):return (37*h+11)&65535
def vector(phase,r,i):
    if r!=1:return 0x6c00+256*r+i
    return 101+13*i
def data(phase,h):
    if h==2051 and phase:return 127 if phase==1 else 36
    if h==2039 and phase==3:return 166
    return original(h)

def expected(s,phase):
    require(phase in range(4),'Unknown phase')
    m={}
    def put(a,v,n=8):
        for i,b in enumerate(v.to_bytes(n,'little')):
            require(a+i not in m,'Overlapping oracle bytes');m[a+i]=b
    p=s['mx_pages'];pte=lambda a,f:(a>>12<<10)|f
    require(p%4096==0 and s['mx_guard_lo']==p-64 and s['mx_guard_hi']==p+20480,'Physical guards')
    for h in range(4096):put(p+2*h,data(phase,h),2)
    entries={1:pte(p+12288,1),2:0x200000cf,512:pte(p+16384,1),1025:pte(p+4096,0xc7)}
    if phase>=2:entries[1024]=pte(p,0xc7)
    for i in range(1536):put(p+8192+8*i,entries.get(i,0))
    for name in ('mx_guard_lo','mx_guard_hi'):
        for i in range(8):put(s[name]+8*i,G)
    for name in ('mx_seed','mx_fault','mx_result'):
        for i in range(8):
            put(s[name]+8*i,G);put(s[name]+448+8*i,G)
        available=name=='mx_seed' or (name=='mx_fault' and phase>=1) or (name=='mx_result' and phase==3)
        vphase=0 if name=='mx_seed' else 1 if name=='mx_fault' else 3
        for r in range(3):
            for i in range(64):put(s[name]+64+128*r+2*i,vector(vphase,r,i) if available else (G>>(16*(i%4)))&65535,2)
    for i in range(128):
        put(s['mx_input']+2*i,101+13*i if i<64 else 0,2)
        slot=(i+1)%3 if i<3 else 3+(i-3+1)%5 if i<8 else i
        put(s['mx_offsets']+2*i,slot*2,2)
    for i in range(130):put(s['mx_out']+2*i,vector(3,1,i-1) if phase==3 and 1<=i<=64 else 0x5b,2)
    for i in range(16):put(s['mx_mask']+i,0x24,1)
    put(s['mx_stride'],MASK64-7)
    satp=(8<<60)|((p+8192)>>12)
    put(s['mx_satp'],satp)
    put(s['mx_count'],0 if phase==0 else 2 if phase==3 else 1)
    put(s['mx_marker'],int(phase==3))
    put(s['mx_restart'],0 if phase==0 else 5)
    put(s['mx_return'],0)
    put(s['mx_prefix_observed'],127 if phase else 0)
    put(s['mx_errors'],0);put(s['mx_unexpected'],0)
    for j in range(6):put(s['mx_post']+8*j,([64,8,0,117,5,0][j] if phase==3 else MASK64))
    for n in range(2):
        live=(n==0 and phase>=1) or (n==1 and phase==3)
        row=[15 if n==0 else 9,s['fault_1_pc'] if n==0 else s['mx_ecall'],VA+4078 if n==0 else 0,
             0x800,satp,8 if n==0 else 64,8,5 if n==0 else 0,117,5,n,pte(p,0xc7) if n else 0]
        for j,v in enumerate(row):
            if live and j==3:continue
            put(s['mx_records']+96*n+8*j,v if live else MASK64)
    return m

def compare(memory,s,phase):
    gold=expected(s,phase)
    for a,v in gold.items():require(a in memory and memory[a]==v,f'Phase{phase} byte {a:x}: expected {v:02x}, actual {memory.get(a)}')
    for n in range(2 if phase==3 else 1 if phase else 0):
        require(readint(memory,s['mx_records']+96*n+24)&0x8000031888==0x800,'Trap privilege/status')
    return len(gold)

def host_check(text):
    want=[]
    for p in range(4):
        want += [f'V {p} {r} {i} {vector(p,r,i):04x}' for r in range(3) for i in range(64)]
        want += [f'D {p} {h} {data(p,h):04x}' for h in range(4096)]
    require(text.splitlines()==want,'Independent Host oracle mismatch')
    return len(want)

def disassemble(text):
    return {int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',text,re.M)}

def window(code,start,count):
    pcs=[]
    for _ in range(count):
        require(start in code,'Missing helper code');pcs.append(start);start+=4 if code[start]&3==3 else 2
    return pcs

def retry_context(s,regs,csr):
    require(csr.get(0x341)==s['fault_1_pc'] and csr.get(8)==5,'Retry changes PC/start')
    require(csr.get(0xc20)==8 and csr.get(0xc21)==8 and csr.get(0x300,0)&0x1800==0x800,'MRET vector/privilege context')
    require([regs.get(i) for i in range(10,16)]==[VA+4118,s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']] and regs.get(28)==MASK64-7,'MRET original GPR context')

def target_access(attempt,access):
    require(attempt in (0,1),'Extra target attempt')
    require(access==([(VA+4102,127)] if attempt==0 else [(VA+4078,166)]),
            'Store target address/value/active-element list differs')

def elf_bytes(path):
    raw=Path(path).read_bytes()
    require(raw[:7]==b'\x7fELF\x02\x01\x01','Expected ELF64 little endian')
    h=struct.unpack_from('<HHIQQQIHHHHHH',raw,16)
    require(h[0]==2 and h[1]==243 and h[8]==56,'Expected RISC-V executable headers')
    memory={}
    for i in range(h[9]):
        kind,flags,off,va,pa,size,memsize,align=struct.unpack_from('<IIQQQQQQ',raw,h[4]+i*h[8])
        if kind!=1:continue
        require(size<=memsize and off+size<=len(raw) and size<2**20,'ELF segment bounds')
        memory.update({va+j:b for j,b in enumerate(raw[off:off+size])})
    # BSS bytes deliberately remain absent until the actual startup writes them.
    return memory

def analyze(path,s,code,elf):
    memory,regs,csr=elf_bytes(elf), {0:0}, {}
    actions=[];points=[];traps=[];events=[];exits=[];helper=[];n=0;firmware=0
    original_window=window(code,s['replay_1'],10)
    unused=window(code,s['replay_0'],10)
    checks=[];console=[];capacity_calls=0;entries=0;mrets=[]
    saved_csrs={};restored=False
    for line in Path(path).open():
        t=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)(?:.*)',line)
        if t:traps.append((t[1],int(t[2],16)))
        match=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not match:continue
        mode,pc,insn,tail=int(match[1]),int(match[2],16),int(match[3],16),match[4];n+=1
        if pc<0x80000000:continue
        firmware+=1
        require(pc in code and code[pc]==insn,f'Retired PC/code mismatch {pc:x}/{insn:x}')
        require(pc!=s['trap_entry'] and pc not in unused,'Unexpected trap or unused original load helper')
        updates={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        access=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc==s['main']: saved_csrs=dict(csr)
        if pc==s['capacity']:capacity_calls+=1
        if pc==s['replay_1']:
            entries+=1
            require([regs.get(i) for i in range(10,16)]==[VA+4118,s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']],'Original six arguments')
        if pc in original_window:
            require(mode==1,'Original helper not S-mode');helper.append(pc)
        if pc==s['fault_1_pc']:
            require(regs.get(10)==VA+4118,'Retry changed original base (double vstart offset)')
            require(regs.get(28)==MASK64-7,'Signed stride register differs')
            require(csr.get(0xc20)==8 and csr.get(0xc21)==8 and csr.get(0x008)==(0 if not events else 5),'Target VL/type/start')
            target_access(len(events),access)
            events.append(dict(pc=hex(pc),vstart=csr[8],addresses=[hex(a) for a,v in access],values=[v for a,v in access],commit=firmware))
            actions.append('target')
        if pc==s['mx_fault_prefix_read']:
            require(insn&0x707f==0x5003 and (insn>>7)&31 in updates,'Prefix observer is not scalar LHU')
            require(access==[(s['mx_pages']+4102,None)] and updates[(insn>>7)&31]==127,'Store prefix not visible before repair')
            require(readint(memory,s['mx_pages']+4102,2)==127,'Observed prefix lacks actual store')
            actions.append('prefix_read')
        if pc==s['mx_checkpoint']:
            phase=readint(memory,s['mx_phase']);checked=compare(memory,s,phase)
            points.append(dict(phase=phase,bytes=checked,commit=firmware));actions.append('checkpoint'+str(phase))
        if pc==s['mx_repair_sfence']:
            require(mode==3 and regs.get((insn>>15)&31)==VA,'Wrong lower-page SFENCE');actions.append('repair_sfence')
        if pc==s['mx_refill_page']:actions.append('refill')
        if pc==s['mx_trap_mret'] and readint(memory,s['mx_marker'])==0:
            retry_context(s,regs,csr)
            mrets.append(dict(commit=firmware,pc=hex(pc),mepc=hex(csr[0x341]),mstatus=hex(csr[0x300]),
                              vl=csr[0xc20],vtype=csr[0xc21],vstart=csr[8],
                              arguments=[hex(regs[i]) for i in range(10,16)],t3=hex(regs[28])))
            actions.append('retry_mret')
        if pc==s['mx_younger_store']:require(mode==1,'Younger privilege');actions.append('younger')
        # Check every scalar comparison call, rather than trusting only its final counter.
        if pc==s['check']:
            require(regs.get(10)==regs.get(11),'Scalar oracle comparison differs')
            checks.append((regs[10],regs[11]))
        for a,v in access:
            if v is None:continue
            if insn&3!=3:
                d=decoder.decode(insn);require(d and d['kind']=='write','Unknown compressed store');width=d['size']
                require(a==(regs.get(d['base'],-1)+d['offset'])&MASK64,'Compressed store address')
            elif insn&127==0x23:
                width=1<<((insn>>12)&7)
                imm=((insn>>25)<<5)|((insn>>7)&31);imm=imm-4096 if imm&2048 else imm
                require(a==(regs.get((insn>>15)&31,-1)+imm)&MASK64,'Scalar store address')
            else:
                require(insn&127==0x27,'Unknown memory write');width={0:1,5:2,6:4,7:8}[(insn>>12)&7]
            physical=s['mx_pages']+a-VA if VA<=a<VA+8192 else a
            for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):memory[physical+i]=b
            if a==s['tohost']:exits.append(v)
            if 'replay_log' in s and s['replay_log']<=a<s['replay_log']+8192:
                if pc>=s['main'] and width==1:console.append(v&255)
        regs.update(updates);regs[0]=0
        csr.update({int(k):int(v,16) for k,v in re.findall(r'\bc([0-9]+)_[^\s]+\s+0x([0-9a-f]+)',tail)})
        # Read-only CSR values are not always emitted as CSR updates by Spike.
        if insn&127==0x73 and (insn>>12)&7 in (1,2,3,5,6,7):
            k=insn>>20;rd=(insn>>7)&31;rs=(insn>>15)&31
            if ((insn>>12)&7)==2 and rs==0 and rd in updates:csr[k]=updates[rd]
        if s.get('mx_completed') in [a for a,v in access]:
            for k in (0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3):
                if k in saved_csrs:require(csr.get(k)==saved_csrs[k],f'CSR restoration {k:x}')
            restored=True
    require(actions==['checkpoint0','target','prefix_read','checkpoint1','repair_sfence','refill','checkpoint2','retry_mret','target','younger','checkpoint3'],'Action order '+str(actions))
    require(traps==[('trap_store_page_fault',s['fault_1_pc']),('trap_supervisor_ecall',s['mx_ecall'])],'Exception ledger '+str(traps))
    require(entries==1 and capacity_calls==1,'Original helper/capacity multiplicity')
    require(helper==original_window[:6]+original_window[5:],'Original helper continuity/retry differs')
    require([e['addresses'] for e in events]==[[hex(VA+4102)],[hex(VA+4078)]],'Actual target active addresses')
    require(exits==[1] and readint(memory,s['mx_completed'])==DONE and readint(memory,s['mx_errors'])==readint(memory,s['mx_unexpected'])==0,'Final exit/errors')
    require(readint(memory,s['mx_checks'])==len(checks)==17275,'Incomplete scalar oracle')
    require(restored,'No CSR restore completion')
    require(firmware<1500000,'Reference instruction bound exceeded')
    return dict(status='REFERENCE_CHECKER_PASS_NOT_DUT',commits=n,firmware_commits=firmware,
                scalar_checks=len(checks),checkpoints=points,actions=actions,targets=events,traps=traps,
                helper_entries=entries,helper_retirements=len(helper),capacity_calls=capacity_calls,retry_mrets=mrets,
                htif=exits,output_elements=64,output_guards=2,memory_bytes=8192,
                linux_signal_equivalence=False,parent96_accepted=False)
