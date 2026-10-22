"""Independent gap71 byte/ELF/trace oracle. No EDA, no coverage waivers."""
import csv
import hashlib
import re
import struct
from pathlib import Path
from custom_backend_lifetime import custom_write_lifetimes

CASE_NAMES = ('gap71_qbs_read','gap71_qbs_fault','gap71_akv_read','gap71_akv_fault')
SCOPES = tuple('ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_'+e+'_engine.i_read_engine' for e in ('qbs','akv'))
TARGETS = {13:((37,'00'),(36,'01')),44:((129,'1101'),(127,'1111')),
           57:((168,'111'),),60:((178,'110'),(177,'111')),
           63:((187,'1110'),(188,'1101')),93:((280,'11'),),95:((287,'010'),)}
M64=(1<<64)-1
GUARD=0x7171717171717171
RUNTIME_SCHEMA='gap71-custom-runtime-v1'
MAX_RETIRED=120000

def require(ok,message):
    if not ok: raise ValueError(message)

def modes(name):
    require(name in CASE_NAMES,'foreign case'); return 'akv' in name,name.endswith('_fault')

def ns(name):
    akv,fault=modes(name); return (4 if fault else 6) if akv else 2

def checks(name):
    _,fault=modes(name)
    return 2+16+12*(1+fault)+9+32*ns(name)+8*(1 if fault else 2)+21

def pages(base,akv,fault):
    b=[bytearray(4096) for _ in range(6)]
    def u64(p,i,v): struct.pack_into('<Q',b[p],i*8,v)
    for p in range(3,6):
        for i in range(512): u64(p,i,0x71a5c39e00000000^(p<<32)^i)
    for p,i,v in ((0,1,((base+4096)>>12)*1024+1),(0,2,0x200000cf),
        (1,0,((base+8192)>>12)*1024+1),(2,0,((base+12288)>>12)*1024+0x43),
        (2,1,((base+20480)>>12)*1024+0x43),(2,2,0 if fault else ((base+16384)>>12)*1024+0x43)):
        u64(p,i,v)
    if akv:
        b[3][:64]=struct.pack('<BBBBHHIIIIQQQQQ',1,1,1,0,64,1,128,128,128,0,
                             0x40001080,0x40002080,0x40002200,0,0)
        for p,off,start,step in ((5,128,0x3000,3),(4,128,0xb400,5),(4,512,0x3800,7)):
            for i in range(64): struct.pack_into('<H',b[p],off+2*i,start+step*i)
    else:
        b[3][:16]=struct.pack('<QQ',0x11112,0x40001080)
        scales=bytes([1]*4+[0]*4+[1]*4)
        b[5][128:272]=struct.pack('<HH',0x3c00,0)+scales+bytes([0x11]*128)
        q=[i%7-3 for i in range(256)]
        b[4][128:420]=struct.pack('<f',1)+struct.pack('<256b',*q)+struct.pack('<16h',*[sum(q[i:i+16]) for i in range(0,256,16)])
    return [list(struct.unpack('<512Q',p)) for p in b]

def seed(i): return 0x719ac35e2608b4df ^ (i*0x100010001)

def outputs(name):
    akv,fault=modes(name); p=pages(0x80040000,akv,False)
    rows=[]
    for j in range(ns(name)):
        row=[seed(i) for i in range(512)]
        if not(fault and j==0):
            if akv:
                stream=(j-fault)%3; row[128:144]=p[4 if stream else 5][(64 if stream==2 else 16):(80 if stream==2 else 32)]
            else: row[128:144]=[0xc0c00000]+[0]*15
        rows.append(row)
    return rows

def digest(words):
    v=0xcbf29ce484222325
    for w in words: v=((v^w)*0x100000001b3)&M64
    return v

def validate_log(log,name,backend):
    _,fault=modes(name)
    expected='GAP71 %s backend=%s snapshots=%d digest=%016x traps=%d'%(name,backend,ns(name),digest(w for p in outputs(name) for w in p),1+fault)
    require(log.splitlines().count(expected)==1,'independent full-VRF digest differs')
    require(re.findall(r'(?m)^(?:PASSED|FAILED): ([^\n]+)$',log)==['%s checks=%d errors=0'%(name,checks(name))],'wrong exact PASS/count')
    require(not re.search(r'(?im)^(?:FAILED|Fatal:|Error:|FAIL:|GAP71_CHECK_FAILED)',log),'runtime failure')
    return dict(checks=checks(name),snapshots=ns(name),full_vrf_words=ns(name)*512,digest=hex(digest(w for p in outputs(name) for w in p)),traps=1+fault,backend=backend)

def metadata(obj,blob,name,software):
    akv,fault=modes(name)
    syms={r['Symbol']['Name']['Name']:r['Symbol']['Value'] for r in obj['Symbols']}
    names=['gap71_pages','gap71_guard_lo','gap71_guard_hi','gap71_site','gap71_s_begin','gap71_s_exit',
           'gap71_m_resume','gap71_handler_entry','gap71_handler_clear','gap71_output','gap71_seed',
           'gap71_records','gap71_csrs','gap71_check_begin','gap71_restore_end']
    names+=['gap71_snapshot_'+n for n in ('vl','vtype','vstart','vcsr','fcsr','satp')]
    if fault: names+=['gap71_pte_repair']
    if akv and not software: names+=['gap71_load_site','gap71_release_site']
    symbols={n:syms[n] for n in names}
    require(all(0x80000000<=v<0x80200000 for v in symbols.values()),'ELF not in RAM prefix')
    base=symbols['gap71_pages']
    require(base%4096==0 and symbols['gap71_guard_lo']+64==base and symbols['gap71_guard_hi']==base+24576,'page guards/layout differ')
    def code(pc,size):
        rows=[r['Section'] for r in obj['Sections'] if r['Section']['Flags']['Value']&4 and r['Section']['Address']<=pc and pc+size<=r['Section']['Address']+r['Section']['Size']]
        require(len(rows)==1,'ambiguous code span'); s=rows[0]; off=s['Offset']+pc-s['Address']; return blob[off:off+size]
    word=lambda pc:int.from_bytes(code(pc,4),'little')
    sites={'gap71_site':0x000f3f83 if akv and software else 0x0005be83 if software else 0x00b5205b if akv else 0x00b5045b,
           'gap71_handler_entry':0x300022f3,'gap71_handler_clear':0x30033073,'gap71_s_exit':0x73}
    if fault: sites['gap71_pte_repair']=0x0062b023
    if akv and not software: sites.update(gap71_load_site=0x0005345b,gap71_release_site=0x0000505b)
    require(all(word(symbols[n])==v for n,v in sites.items()),'linked site instruction differs')
    require(symbols['gap71_handler_clear']==symbols['gap71_handler_entry']+8 and word(symbols['gap71_handler_entry']+4)==0x20337,'handler memory before MPRV clear')
    if not software:
        boot=syms['gap71_boot_mpp']
        require(boot==syms['rvtest_init'] and
                [word(boot+i*4) for i in range(3)]==[0x000022b7,0x80028293,0x3002a073],
                'DUT boot must set MPP=M before CRT MRET')
        auipc,addi=word(boot+12),word(boot+16)
        require(auipc&0xfff==0x297 and addi&0xfffff==0x28293 and
                word(boot+20)==0x30529073 and word(boot+24)==0x00008067,
                'DUT boot must install mtvec and return without a stack frame')
        hi=auipc&0xfffff000;hi-=1<<32 if hi&(1<<31) else 0
        lo=addi>>20;lo-=4096 if lo&2048 else 0
        require(boot+12+hi+lo==symbols['gap71_handler_entry'],'DUT boot mtvec target differs')
        init_pc=syms['_start'];reset=code(init_pc,syms['trap_vector']-init_pc)
        mret=reset.find(bytes.fromhex('73002030'))
        calls=[]
        for i in range(0,mret-13,2):
            a,b=[int.from_bytes(reset[i+j:i+j+4],'little') for j in (0,4)]
            if a&0xfff!=0x297 or b&0xfffff!=0x28293:continue
            h=a&0xfffff000;h-=1<<32 if h&(1<<31) else 0
            l=b>>20;l-=4096 if l&2048 else 0
            if init_pc+i+h+l==boot:
                require(reset[i+8:i+14]==bytes.fromhex('638302008292'),'CRT init call differs')
                calls.append(init_pc+i+12)
        require(mret>=0 and len(calls)==1,'DUT init hook must execute before CRT MRET')
        symbols.update(gap71_boot_mpp=boot,gap71_boot_call=calls[0])
    return dict(symbols=symbols,words=sites,software_reference=software,
                s_program_sha256=hashlib.sha256(code(symbols['gap71_s_begin'],symbols['gap71_s_exit']+4-symbols['gap71_s_begin'])).hexdigest())

def final_memory(name,info):
    s=info['symbols'];akv,_=modes(name); p=pages(s['gap71_pages'],akv,False)
    result={s['gap71_pages']+j*4096+i*8:w for j,page in enumerate(p) for i,w in enumerate(page)}
    for key in ('gap71_guard_lo','gap71_guard_hi'):
        result.update({s[key]+i*8:(GUARD if key.endswith('_lo') else GUARD^M64)^i for i in range(8)})
    for key,count in (('gap71_output',ns(name)),('gap71_seed',1)):
        addr=s[key]; result.update({addr+i*8:GUARD^i for i in range(8)})
        result.update({addr+64+count*4096+i*8:(GUARD^M64)^i for i in range(8)})
        rows=outputs(name) if key=='gap71_output' else [[seed(i) for i in range(512)]]
        result.update({addr+64+j*4096+i*8:w for j,row in enumerate(rows) for i,w in enumerate(row)})
    return result

def spike_trace(trace,name,info):
    s=info['symbols'];_,fault=modes(name)
    commits=[(m.start(),int(m[1]),int(m[2],16),int(m[3],16),m[4]) for m in re.finditer(r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$',trace)]
    require(0<len(commits)<=MAX_RETIRED,'empty/over-budget Spike trace')
    traps=[(m.start(),m[1],int(m[2],16)) for m in re.finditer(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)]
    wanted=([('trap_load_page_fault',s['gap71_site'])] if fault else [])+[('trap_supervisor_ecall',s['gap71_s_exit'])]
    require([(t[1],t[2]) for t in traps]==wanted,'trap sequence/ELF identity differs')
    memory=final_memory(name,info); reads=set(); checking=False; satp=None; handlers=0; clears=0; repairs=[]; sites=0
    for pos,mode,pc,word,tail in commits:
        require(word&127!=91,'Spike executed a custom instruction')
        writes={int(c):int(v,16) for c,v in re.findall(r'\bc([0-9]+)_\w+\s+0x([0-9a-f]+)',tail)}
        satp=writes.get(0x180,satp)
        if pc==s['gap71_check_begin']: checking=True
        if pc==s['gap71_restore_end']: checking=False
        if pc==s['gap71_site']:
            require(mode==1 and satp==(8<<60)|(0x71<<44)|(s['gap71_pages']>>12),'not actual S/Sv39 software probe');sites+=1
        if pc==s['gap71_handler_entry']: handlers+=1
        if pc==s['gap71_handler_clear']: clears+=1; require('mem ' not in tail,'MPRV clear accessed memory')
        if fault and pc==s['gap71_pte_repair']:
            repairs+=re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)',tail)
        ld64=(word&127==3 and (word>>12)&7==3) or (word&3 in (0,2) and (word>>13)&7==3)
        if checking and ld64:
            mem=re.findall(r'\bmem 0x([0-9a-f]+)(?![0-9a-f])',tail)
            changes=[int(v,16) for _,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)]
            for a in mem:
                address=int(a,16)
                if address in memory:
                    require(changes==[memory[address]],'full memory read differs at '+hex(address)); reads.add(address)
    require(handlers==clears==len(wanted) and sites==(1 if fault else 2),'handler/site execution count differs')
    require(reads==set(memory),'incomplete PTE/data/guard/VRF readback')
    if fault: require(repairs==[(format(s['gap71_pages']+8208,'016x'),format(memory[s['gap71_pages']+8208],'016x'))],'not exact one-PTE repair')
    return dict(status='PASS',retired=len(commits),full_compared_words=len(reads),traps=len(wanted),
                actual_execution='S/Sv39 payload; M handler/restore',custom_instructions_executed=0,
                scope='Software reference only; no accelerator/MMU internal condition claim')

def runtime_traces(commit_path,vector_path,name,info):
    from ara_verify.vector_commit import _parse_vector_trace,_architectural_bytes
    akv,fault=modes(name);s=info['symbols']; phases=1 if fault else 2
    expected=[(info['words']['gap71_site'],int(fault))] if fault else []
    for _ in range(phases):
        expected.append((info['words']['gap71_site'],0))
        if akv: expected.extend([(info['words']['gap71_load_site'],0)]*3)
    if akv: expected.append((info['words']['gap71_release_site'],0))
    pending={}; custom=[]; retired=[]; last=0; req=resp=0; snapshots=[];handler=[];starts=[]
    memory=final_memory(name,info);reads=set();checking=False
    csr_sites={s['gap71_snapshot_'+n]:v for n,v in (('vl',16),('vtype',24),('vstart',0),('vcsr',5),('fcsr',0),('satp',(8<<60)|(0x71<<44)|(s['gap71_pages']>>12)))}
    with Path(commit_path).open() as stream:
        for r in csv.DictReader(stream):
            event=r['event'];cycle=int(r['cycle']); require(cycle>=last,'cycle regression');last=cycle
            word=int(r['insn'],16); pc=int(r['pc'],16)
            if event=='arch_start' and word&127==91:starts.append((int(r['order']),word))
            if event=='retire':
                if pc==s['gap71_check_begin']:checking=True
                if pc==s['gap71_restore_end']:checking=False
                address=int(r['mem_addr'],16)
                if checking and int(r['mem_rmask'],16)==255 and address in memory:
                    require(not int(r['trap']) and int(r['rd_wdata'],16)==memory[address],'independent complete memory readback differs');reads.add(address)
            if event=='cvx_req':
                key=int(r['trans_id']);require(key not in pending,'duplicate request');pending[key]=word;req+=1
                if word&127==91: custom.append([word,None])
            elif event=='cvx_resp':
                key=int(r['trans_id']);require(key in pending,'orphan response');w=pending.pop(key);resp+=1
                if w&127==91:
                    idx=[i for i,c in enumerate(custom) if c[0]==w and c[1] is None];require(len(idx)==1,'ambiguous custom response');custom[idx[0]][1]=int(r['trap'])
                else: require(int(r['trap'])==0,'noncustom vector exception')
            elif event=='retire' and word&127==91:
                require(not int(r['trap']),'faulting custom retired');retired.append((pc,word))
            if event=='retire' and pc in csr_sites:
                require(not int(r['trap']) and int(r['rd_wdata'],16)==csr_sites[pc],'custom CSR snapshot differs');snapshots.append(pc)
            if event=='retire' and s['gap71_handler_entry']<=pc<=s['gap71_handler_clear']:
                handler.append((pc,word))
                if pc==s['gap71_handler_entry']:require(int(r['rd_wdata'],16)&0x7e7faa==0x6e00,'trap not from exact S privilege/FS/VS; MPRV/SUM/MXR/IRQ contaminated')
    require(not pending and req==resp and [tuple(c) for c in custom]==expected,'custom request/outcome conservation differs')
    pcs={v:s[k] for k,v in info['words'].items() if k in ('gap71_site','gap71_load_site','gap71_release_site')}
    require(retired==[(pcs[w],w) for w,t in expected if not t],'custom retirement does not match ELF')
    require(snapshots==list(csr_sites)*phases,'snapshot retirement count/order differs')
    require(handler==[(s['gap71_handler_entry'],0x300022f3),(s['gap71_handler_entry']+4,0x20337),(s['gap71_handler_clear'],0x30033073)]*(1+fault),'strict register-only trap entry differs')
    require(reads==set(memory),'missing full scalar PTE/data/guard/VRF readback')
    lanes,vlen,activities=_parse_vector_trace(Path(vector_path));require((lanes,vlen)==(4,1024),'VRF configuration differs')
    require([w for _,w in starts]==[w for w,_ in expected],'custom architectural sequence differs')
    custom_write_lifetimes(vector_path,starts)
    selected=[a for _,a in sorted(activities.items()) if a.instruction&127==91]
    require([a.instruction for a in selected]==[w for w,_ in expected],'vector custom sequence differs')
    seeds=[]
    for _,a in sorted(activities.items()):
        if a.instruction&127==91:continue
        vals={k:v for k,(v,_) in _architectural_bytes(a.writes,lanes,vlen).items()}
        if vals:
            r=(a.instruction>>7)&31; want=struct.pack('<16Q',*[seed(r*16+i) for i in range(16)])
            require(a.instruction&127==7 and vals=={(r,i):v for i,v in enumerate(want)},'noncustom VRF write differs');seeds.append(r)
    require(seeds==list(range(32)),'missing full seed VRF writes')
    output_bytes=[]; stream=0
    for a,(w,t) in zip(selected,expected):
        require(a.allocations==a.completions==1,'vector allocation/completion differs')
        vals={k:v for k,(v,_) in _architectural_bytes(a.writes,lanes,vlen).items()}
        copy=(akv and w==0x0005345b) or (not akv and not t)
        if not copy: require(not vals,'FULL/RELEASE/fault wrote VRF');continue
        row=outputs(name)[(int(fault)+stream) if akv else (int(fault)+len(output_bytes))]
        want=struct.pack('<16Q',*row[128:144]);require(vals=={(8,i):v for i,v in enumerate(want)},'independent custom VRF bytes differ')
        output_bytes.append(want.hex());stream+=1
    return dict(status='PASS',requests=req,responses=resp,last_cycle=last,custom=expected,
                full_scalar_compared_words=len(reads),
                exact_destination_bytes=128*len(output_bytes),destination_sha256=hashlib.sha256(''.join(output_bytes).encode()).hexdigest(),
                internal_target_hits_measured=False)

def runtime_perf(log,name):
    akv,fault=modes(name);tag='AKV' if akv else 'QBS'
    rows=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in re.findall(r'(?m)^\['+tag+r'_PERF\] (.*)$',log)]
    phases=1 if fault else 2
    expected=([(0,1)] if fault else [])
    for _ in range(phases):expected.extend([(0,0)]+([(2,0)]*3 if akv else []))
    if akv:expected.append((3,0))
    require(len(rows)==len(expected),'PERF command count differs')
    for r,(command,isfault) in zip(rows,expected):
        require(r['success']==1-isfault and r['fault']==isfault and r['validation_fault']==0 and r['read_fault']==(2 if isfault else 0),'not exact successful/MMU payload-fault phenotype')
        if akv:require(r['command']==command,'AKV command identity differs')
        if isfault:require(r['translations']>0,'fault bypassed MMU')
        elif command==0:
            require(r['read_ranges']==r['translations']==(4 if akv else 3),'not all translated ranges')
            require(r['read_payload_bytes' if akv else 'payload_bytes']==(448 if akv else 452),'payload bytes differ')
        if akv:require(r['context_ready']==int(not isfault and command!=3),'AKV context cleanup differs')
        elif isfault:require(r['commit_groups']==0,'fault committed QBS VRF')
    return dict(status='PASS',commands=len(rows),mmu_faults=int(fault),rows=rows,
                scope='Translation request/terminal phenotype; not a claim of cold TLB hits or internal condition rows')
