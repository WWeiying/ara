#!/usr/bin/env python3
"""Independent sparse-memory, linked instruction and Spike oracle for gap68."""
import hashlib
import re

NAME = 'rvv:sv39_gap68_warm_permissions_pmp0'
CHECKS, MAX_RETIRED = 71, 35000
MASK64 = (1 << 64)-1
# Match the project's supported writable status fields, not SD/UXL/SXL.
STATUS_MASK = (3<<11)|(1<<7)|(1<<3)|(1<<17)|(3<<13)|(3<<9)|(1<<1)|(1<<5)|\
              (1<<8)|(1<<18)|(1<<19)|(1<<20)|(1<<21)|(1<<22)|(1<<39)
SSTATUS_MASK = (3<<13)|(3<<9)|(1<<1)|(1<<5)|(1<<8)|(1<<18)|(1<<19)
TAGS = (0x6811681168116811, 0x6822682268226822)
GUARD = 0x6b6b6b6b6b6b6b6b
WORDS = dict(gap68_load_a=0x5b783, gap68_store_a=0x105b023,
             gap68_load_b=0x5b783, gap68_store_b=0x105b023,
             gap68_handler_entry=0x300022f3, gap68_handler_clear=0x30033073)
CSRS = (0x300,0x100,0x304,0x305,0x341,0x342,0x343,0x180,0x302,0x303,0x340,
        0x105,0x141,0x142,0x143,0x140,0xc20,0xc21,0x008,0x00f,0x003)

def require(ok, message):
    if not ok: raise ValueError(message)

def expected_pages(base):
    pages = [[0]*512 for _ in range(3)] + [[tag ^ w for w in range(512)] for tag in TAGS]
    pages[0][1] = ((base+4096)//4096)*1024+1
    pages[1][0] = ((base+8192)//4096)*1024+1
    pages[2][0] = ((base+12288)//4096)*1024+0xc3
    pages[2][1] = ((base+16384)//4096)*1024+0x47
    return pages

def expected_command(tool, elf):
    return [tool,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',elf]

def validate_pmp_dts(text):
    require(re.findall(r'riscv,pmpregions\s*=\s*<([0-9]+)>;',text)==['0'],'not one PMP0 hart')

def metadata(obj, blob):
    symbols = {r['Symbol']['Name']['Name']:r['Symbol']['Value'] for r in obj['Symbols']}
    names = list(WORDS)+['gap68_pages','gap68_guard_lo','gap68_guard_hi','records','trap_count',
        'abi_bad','gap68_payload_begin','gap68_payload_end','gap68_check_begin','gap68_restore_end','gap68_resume']
    sym = {n:symbols[n] for n in names}
    p = sym['gap68_pages']
    require(p%4096==0 and 0x80000000<=p and sym['gap68_guard_hi']+64<=0x80200000,'bad RAM placement')
    require(sym['gap68_guard_lo']+64==p and sym['gap68_guard_hi']==p+20480,'guards not adjacent')
    require(all(0x80000000<=v<0x80200000 for v in sym.values()),'symbol outside RAM prefix')
    def span(start,end):
        matches=[]
        for row in obj['Sections']:
            s=row['Section']
            if s['Flags']['Value']&4 and s['Address']<=start<end<=s['Address']+s['Size']:
                off=s['Offset']+start-s['Address']; matches.append(blob[off:off+end-start])
        require(len(matches)==1,'ambiguous executable span'); return matches[0]
    sites={n:dict(pc=hex(sym[n]),word=hex(int.from_bytes(span(sym[n],sym[n]+4),'little'))) for n in WORDS}
    require(all(sites[n]['word']==hex(w) for n,w in WORDS.items()),'linked instruction differs')
    hashes={}
    for suffix in ('a','b'):
        start,end=sym['gap68_load_'+suffix],sym['gap68_store_'+suffix]+4
        require(end-start==12,'not adjacent load/xor/store')
        payload=span(start,end)
        require(int.from_bytes(payload[4:8],'little')==0x00c7c833,'not dependent XOR')
        hashes[suffix]=hashlib.sha256(payload).hexdigest()
    require(sym['gap68_handler_clear']-sym['gap68_handler_entry']==8,'memory before MPRV clear')
    require(int.from_bytes(span(sym['gap68_handler_entry']+4,sym['gap68_handler_clear']),'little')==0x00020337,
            'wrong handler MPRV clear mask')
    return dict(symbols=sym,sites=sites,payload_sha256=hashes,data_words=1024,pte_words=1536,guard_words=16)

def check_log(log, source):
    require(re.findall(r'^gap35 checks=(\d+) failures=0$',log,re.M)==[str(CHECKS)],'wrong checks/failures')
    require(log.splitlines().count('PASSED: '+source+'!')==1 and
        sum(l.startswith('PASSED:') for l in log.splitlines())==1,'wrong PASS source')
    require(not re.search(r'(?im)^(?:FAIL|check=|Fatal:|Error:)',log),'failure in log')

def trace_check(trace, info):
    sym=info['symbols']
    commits=[(m.start(),int(m[1]),int(m[2],16),int(m[3],16),m[4]) for m in re.finditer(
        r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$',trace)]
    require(len(commits)>0,'empty retirement trace')
    require(not re.search(r'(?m)^core\s+[1-9][0-9]*:',trace),'extra hart')
    traps=[(m.start(),m[1],int(m[2],16)) for m in re.finditer(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)]
    require([(t[1],t[2]) for t in traps]==[('trap_store_page_fault',sym['gap68_store_'+s]) for s in ('a','b')],
            'not exactly two linked store page faults')
    original, restored, recorded, reads = {}, {}, {}, set()
    active=finished=checking=restore_done=False
    begin=end=check=restore=0
    loads=[]; clear_count=resume_count=0
    gpr={0:0}; status=None; root=None; pending=None; stage=None; trap_index=0
    final_memory={sym['gap68_pages']+p*4096+w*8:v for p,page in enumerate(expected_pages(sym['gap68_pages']))
                  for w,v in enumerate(page)}
    final_memory.update({sym['gap68_guard_lo']+w*8:GUARD^w for w in range(8)})
    final_memory.update({sym['gap68_guard_hi']+w*8:(GUARD^MASK64)^w for w in range(8)})
    for index,(pos,mode,pc,word,tail) in enumerate(commits):
        require(mode==3,'actual execution left M-mode')
        if pc==sym['gap68_payload_begin']: begin+=1; active=True
        if pc==sym['gap68_payload_end']: end+=1; active=False; finished=True
        if pc==sym['gap68_check_begin']: check+=1; checking=True
        if pc==sym['gap68_restore_end']: restore+=1; restore_done=True
        changes={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        mem=[(int(a,16),int(v,16) if v else None) for a,v in
             re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if word&0x7f==0x73 and (word>>12)&7:
            csr=word>>20
            require(not 0x3a0<=csr<=0x3ef,'PMP CSR access')
            if ((word>>12)&7)==2 and (word>>15)&31==0 and changes and csr in CSRS:
                value=next(iter(changes.values()))
                if not active and not finished: original.setdefault(csr,value)
                if checking and not restore_done: restored[csr]=value
        if active:
            require(word&0x7f not in (7,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57),'FP/vector payload')
            require(not ((word&3) in (0,2) and (word>>13)&7 in (1,5)),'compressed FP payload')
            if status is not None and status&(1<<17) and (status>>11)&3==1 and mem:
                require(pc in (sym['gap68_load_a'],sym['gap68_load_b']),'foreign translated memory access')
        if pending is not None:
            # Trap entry must start with the audited register-only clear sequence.
            expected_pc=sym['gap68_handler_entry']+4*stage
            require(pc==expected_pc and not mem,'handler accessed memory before clearing MPRV')
            require(word==(0x300022f3,0x20337,0x30033073)[stage],'wrong handler clear instruction')
            if stage==0:
                require(changes=={5:pending},'trapped status not preserved in t0')
            if stage==2:
                require(re.findall(r'\bc768_mstatus\s+0x([0-9a-f]+)',tail)==[format(pending&~(1<<17),'016x')],
                        'handler did not clear only MPRV')
                require(pc==sym['gap68_handler_clear'],'wrong clear site'); clear_count+=1; pending=None
            stage = None if pending is None else stage+1
        for suffix in ('a','b'):
            if pc==sym['gap68_load_'+suffix]:
                p=0 if suffix=='a' else 1
                require(active and len(loads)==p and word==WORDS['gap68_load_'+suffix],'extra/reordered load')
                setup=(original[0x300]&~STATUS_MASK)|(3<<13)|(3<<9)|(1<<17)|(1<<11)|((1<<19) if p==0 else 0)
                expected_root=(8<<60)|(0x68<<44)|(sym['gap68_pages']>>12)
                require(status is not None and status&STATUS_MASK==setup&STATUS_MASK and root==expected_root,'wrong MPRV/S/MXR/SATP setup')
                require(gpr.get(11)==0x40000000+4096*p and gpr.get(12)==(0x101 if p==0 else 0x202),'wrong VA/XOR mask')
                require(gpr.get(14)==status and gpr.get(17)==root,'setup CSR snapshots differ')
                require(mem==[(0x40000000+4096*p,None)] and changes=={15:TAGS[p]},'load address/sentinel differs')
                loads.append(p)
                following=[c for c in commits if pos<c[0]<traps[p][0]]
                require(len(following)==1 and following[0][2]==pc+4 and following[0][3]==0xc7c833 and
                    re.search(r'\bx16\s+0x%016x\b'%(TAGS[p]^(0x101 if p==0 else 0x202)),following[0][4]) and
                    'mem ' not in following[0][4],'load/store interval not one dependent XOR')
            require(pc!=sym['gap68_store_'+suffix],'faulting store incorrectly retired')
        if pc==sym['gap68_resume']: resume_count+=1
        if active:
            for address,value in mem:
                if sym['records']<=address<sym['records']+160 and value is not None:
                    require(address not in recorded,'trap record written twice'); recorded[address]=value
        if checking and not restore_done:
            for address,value in mem:
                if address in final_memory:
                    require(value is None and len(changes)==1 and next(iter(changes.values()))==final_memory[address],
                            'full-region comparison read mismatch')
                    reads.add(address)
        # Architectural trap updates are not a retirement, so model them at the event boundary.
        csr_writes={int(c):int(v,16) for c,v in re.findall(r'\bc([0-9]+)_\w+\s+0x([0-9a-f]+)',tail)}
        status=csr_writes.get(0x300,status); root=csr_writes.get(0x180,root)
        gpr.update(changes)
        if trap_index<len(traps) and pos<traps[trap_index][0] and (
                commits[index+1][0] if index+1<len(commits) else len(trace))>traps[trap_index][0]:
            require(active and len(loads)==trap_index+1 and status is not None,'trap outside probe')
            status=(status&~((3<<11)|(1<<7)|(1<<3)))|(3<<11)
            pending=status; stage=0; trap_index+=1
    require((begin,end,check,restore,clear_count,resume_count,trap_index)==(1,1,1,1,2,2,2),'boundary/trap recovery count differs')
    require(pending is None and reads==set(final_memory),'missing final reads/handler completion')
    require(set(original)==set(CSRS) and set(restored)==set(CSRS),'missing CSR snapshots/restoration reads')
    for csr in CSRS:
        mask=STATUS_MASK if csr==0x300 else SSTATUS_MASK if csr==0x100 else MASK64
        want=original[csr]&~8 if csr==0x300 else original[csr]
        require(restored[csr]&mask==want&mask,'restored CSR differs: '+hex(csr))
    clean=(original[0x300]&~STATUS_MASK)|(3<<13)|(3<<9)
    root=(8<<60)|(0x68<<44)|(sym['gap68_pages']>>12)
    for p,suffix in enumerate(('a','b')):
        setup=clean|(1<<17)|(1<<11)|((1<<19) if p==0 else 0)
        want=[15,sym['gap68_store_'+suffix],0x40000000+4096*p,(setup&~(3<<11))|(3<<11),root,
              TAGS[p],TAGS[p]^(0x101 if p==0 else 0x202),setup,root,1]
        for j,v in enumerate(want):
            addr=sym['records']+(p*10+j)*8
            mask=STATUS_MASK if j in (3,7) else MASK64
            require(addr in recorded and recorded[addr]&mask==v&mask,'trap record differs: %d/%d'%(p,j))
    require(len(commits)<=MAX_RETIRED,'over-budget retirement trace')
    return dict(status='PASS',retired=len(commits),retired_limit=MAX_RETIRED,store_traps=2,load_probes=2,
                trap_record_words=20,final_compared_words=len(reads),data_words=1024,pte_words=1536,
                guard_words=16,pmp_regions=0,pmp_csr_accesses=0,actual_privilege='M',
                coverage_gain_required=False,warm_hit_coverage_measured=False)
