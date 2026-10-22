"""One full Spike traversal: actual code, stores, full data, helpers and traps."""
import importlib.util
import json
import re
import struct
from pathlib import Path
import model as m
from spill_guard import StoreGuard
from prepare import code, window

DECODER=m.HERE.parents[4]/'verification/coverage/scoped_rv64c_memory.py'
spec=importlib.util.spec_from_file_location('segment144_memory_decoder',DECODER)
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
MASK=(1<<64)-1
COMMIT=re.compile(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')
ATTEMPT=re.compile(r'^core\s+0:\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)')
REG=re.compile(r'\bx([0-9]+)\s+0x([0-9a-f]+)')
ACCESS=re.compile(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?')
CSR=re.compile(r'\bc([0-9]+)_[^\s]+\s+0x([0-9a-f]+)')

def elf_memory(elf):
    b=Path(elf).read_bytes();m.require(b[:7]==b'\x7fELF\x02\x01\x01','ELF64 LE')
    h=struct.unpack_from('<HHIQQQIHHHHHH',b,16);memory={}
    m.require(h[1]==243 and h[8]==56,'RISC-V ELF layout')
    for i in range(h[9]):
        kind,flags,off,va,pa,size,msize,align=struct.unpack_from('<IIQQQQQQ',b,h[4]+i*56)
        if kind==1:
            m.require(size<=msize and off+size<=len(b),'ELF PT_LOAD bounds')
            memory.update({va+j:v for j,v in enumerate(b[off:off+size])})
    return memory

def read(memory,a,n=8):
    m.require(all(a+i in memory for i in range(n)),f'Missing actual bytes {a:x}/{n}')
    return int.from_bytes(bytes(memory[a+i] for i in range(n)),'little')

def equal_bytes(memory,a,want,reason):
    for i,v in enumerate(want):
        m.require(memory.get(a+i)==v,f'{reason} byte{i}: got{memory.get(a+i)} expected{v}')

def scalar(insn):
    if insn&3!=3:return d.decode(insn)
    op=insn&127;f=(insn>>12)&7
    if op==3 and f in range(7):
        imm=insn>>20;imm-=4096 if imm&2048 else 0
        return dict(kind='read',size=1<<(f&3),base=(insn>>15)&31,register=(insn>>7)&31,offset=imm,signed=f<4)
    if op==35 and f in range(4):
        imm=((insn>>25)<<5)|((insn>>7)&31);imm-=4096 if imm&2048 else 0
        return dict(kind='write',size=1<<f,base=(insn>>15)&31,register=(insn>>20)&31,offset=imm)
    return None

def analyze(raw,out):
    s=json.loads((out/'spike.symbols.json').read_text());c=code((out/'spike.dis').read_text())
    proof=json.loads((out/'source_proof.json').read_text())['backends']['spike']['helpers']
    helpers={name:r['pcs'] for name,r in proof.items()}
    allpcs={pc:name for name,pcs in helpers.items() for pc in pcs}
    targets={s['target_%d'%i]:i for i in range(8)}
    memory=elf_memory(out/'spike.elf');regs={0:0};csr={};saved={}
    store_guard=StoreGuard()
    current=-1;checkpoint=0;active=None;next_index=0;capacity=0;helpercalls=[]
    targets_seen=[];traps=[];rows=fw=0;numerical=capability=0;comparisons=0
    compare=False;actual_reads=[];expected_reads=[];reports=[];exits=[]
    configs=m.cases();gold=[m.expected(cfg) for cfg in configs]
    firmware_exited=False;parking=0
    exit_pcs=window(c,s['replay_exit'],7)
    m.require(c[exit_pcs[-1]]==0xa001,'Actual HTIF park instruction')
    def val(name):return read(memory,s[name])
    with Path(raw).open() as f:
        for line in f:
            attempt=ATTEMPT.match(line)
            if attempt and int(attempt[1],16) in targets:
                pc=int(attempt[1],16);cfg=configs[current]
                m.require(active=='op_%d'%cfg['op'] and helpers[active][next_index]==pc,'Target outside original helper window')
                m.require(targets[pc]==cfg['op'] and csr.get(0xc20)==cfg['vl'] and csr.get(0xc21)==9 and csr.get(8)==0,'Target VL/type/start')
                m.require(val('mx_scene')==1,'Target not preceded by actual phase1 store')
                targets_seen.append(dict(case=current,pc=pc,vl=csr[0xc20],phase=1))
            tr=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
            if tr:
                name,pc=tr[1],int(tr[2],16);traps.append(dict(case=current,trap=name,pc=pc))
                if pc in targets:
                    m.require(active is not None and helpers[active][next_index]==pc,'Fault helper boundary')
                    active=None;next_index=0
                else:m.require(pc==s['mx_ecall'],'Non-target/non-completion trap')
            match=COMMIT.match(line)
            if not match:continue
            mode,pc,insn,tail=int(match[1]),int(match[2],16),int(match[3],16),match[4]
            rows+=1
            if pc<0x80000000:continue
            fw+=1;m.require(c.get(pc)==insn,f'Actual PC/code {pc:x}/{insn:x}')
            if firmware_exited:
                m.require(insn==0xa001 and pc==exit_pcs[-1],'Only known HTIF parking after exit')
                parking+=1
            m.require(pc!=s['trap_entry'],'Unexpected bootstrap handler')
            updates={int(r):int(v,16) for r,v in REG.findall(tail)}
            access=[(int(a,16),int(v,16) if v else None) for a,v in ACCESS.findall(tail)]
            if pc==s['main']:saved=dict(csr)
            if pc==s['mx_checkpoint']:
                cfg=configs[val('mx_case')]
                if checkpoint%2==0:
                    m.require(cfg['id']==current+1 and active is None,'Original144 order, no skipped predecessor')
                    current=cfg['id'];compare=False;actual_reads=[];expected_reads=[]
                    for name,want in [('input',m.INPUT),('memory',m.FILL if cfg['store'] else m.MEMORY),
                                      ('output',m.FILL),('expected',gold[current])]:
                        equal_bytes(memory,s['mx_'+name],want,'Full child reset '+name)
                    equal_bytes(memory,s['mx_mask'],bytes([0 if cfg['off'] else 255])*128,'Full predicate')
                    m.require(val('mx_scene')==0 and val('mx_return')==MASK and val('mx_outcome')==0,'Reset phase/return/outcome')
                else:
                    m.require(cfg['id']==current and active is None and len(targets_seen)==current+1,'Completion ownership/count')
                    record=[read(memory,s['mx_records']+current*80+8*j) for j in range(10)]
                    m.require(record[6]&0x1800==0x800 and record[7]==val('mx_satp'),'Actual S-mode/Sv39 trap')
                    if val('mx_outcome')==1:
                        m.require(record[:5]==[0,9,cfg['vl'] if cfg['store'] else 128,9,s['mx_ecall']] and
                                  record[5]==0 and record[8:]==[2,0],'Numerical completion CSR/phase')
                        equal_bytes(memory,s['mx_memory' if cfg['store'] else 'mx_output'],gold[current],'Full8192 numerical oracle')
                        post=[read(memory,s['mx_post']+current*32+8*j) for j in range(4)]
                        m.require(post==[cfg['vl'] if cfg['store'] else 128,9,0,0],'Real returned CSR')
                        m.require(actual_reads==list(range(1024)) and expected_reads==list(range(1024)),'Full scalar loads, no omitted tail/guards')
                        numerical+=1
                    else:
                        m.require(val('mx_outcome')==2 and cfg['offset'] and cfg['vl'] and not cfg['off'] and
                                  record[3]==(6 if cfg['store'] else 4) and record[4]==s['target_%d'%cfg['op']] and
                                  record[8]==1 and record[9]==MASK,'Strict target-only capability branch')
                        m.require(not actual_reads and not expected_reads,'Invented trapped-child oracle')
                        m.require(all(read(memory,s['mx_post']+current*32+8*j)==MASK for j in range(4)),'Invented successful return')
                        capability+=1
                    m.require(val('mx_errors')==val('mx_fatal')==0,'Actual failure retained')
                    reports.append(dict(case=current,outcome=val('mx_outcome'),trap=record))
                checkpoint+=1
            if pc==s['capacity']:capacity+=1
            if pc in allpcs:
                name=allpcs[pc]
                if pc==helpers[name][0]:
                    m.require(active is None,'Overlapping helper invocation');active=name;next_index=0
                    if name!='capacity':
                        cfg=configs[current]
                        args=[s['mx_input']+64,s['mx_output']+64,s['mx_mask'],cfg['vl'],128,
                              s['mx_memory']+cfg['base'],cfg['stride']&MASK,s['mx_scene']]
                        m.require(name=='op_%d'%cfg['op'] and [regs.get(i) for i in range(10,18)]==args and mode==1,'Original eight arguments/helper/order')
                        helpercalls.append(current)
                m.require(active==name and helpers[name][next_index]==pc,'Original contiguous helper instructions')
                next_index+=1
                if next_index==len(helpers[name]):active=None;next_index=0
            if pc==s['mx_compare']:compare=True
            if compare and pc>=s['mx_allowed']:compare=False
            desc=scalar(insn)
            for a,v in access:
                if desc:
                    width=desc['size'];m.require(a==(regs.get(desc['base'],-2)+desc['offset'])&MASK,'Scalar effective address')
                    if desc['kind']=='write':
                        store_guard.check(v,regs,desc,pc,mode,current,a,s,c)
                    else:
                        m.require(v is None and desc['register'] in updates,'Actual scalar load data missing')
                        got=updates[desc['register']]&((1<<(width*8))-1)
                        signed=desc.get('signed',width==4)
                        full=(got-(1<<(8*width)))&MASK if signed and got>>(8*width-1) else got
                        m.require(updates[desc['register']]==full,'Scalar load sign/zero extension')
                        m.require(read(memory,a,width)==got,'Scalar read disagrees with actual memory')
                        if compare:
                            cfg=configs[current];base=s['mx_memory' if cfg['store'] else 'mx_output']
                            for b,indices in ((base,actual_reads),(s['mx_expected'],expected_reads)):
                                if b<=a<b+8192:
                                    m.require(width==8 and (a-b)%8==0,'Packed oracle scalar width/alignment')
                                    idx=(a-b)//8;indices.append(idx)
                                    want=int.from_bytes(gold[current][idx*8:idx*8+8],'little')
                                    m.require(got==want,'Actual numerical word mismatch')
                                    if b==base:comparisons+=1
                        continue
                else:
                    m.require(insn&127 in (7,39),'Unknown memory operation')
                    width={0:1,5:2,6:4,7:8}[(insn>>12)&7]
                    if v is None:continue
                for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):memory[a+i]=b
                if a==s['tohost']:
                    exits.append(v);firmware_exited=True
            regs.update(updates);regs[0]=0
            csr.update({int(k):int(v,16) for k,v in CSR.findall(tail)})
            if insn&127==0x73 and (insn>>12)&7==2 and (insn>>15)&31==0 and (insn>>7)&31 in updates:
                csr[insn>>20]=updates[(insn>>7)&31]
    m.require(checkpoint==288 and current==143 and helpercalls==list(range(144)) and capacity==1,'Complete144/helpers/checkpoints')
    m.require(len(targets_seen)==len(traps)==144 and len(reports)==144,'One actual target/trap outcome per original call')
    m.require(numerical+capability==144 and val('mx_noactive')==96 and
              val('mx_supported')==numerical and val('mx_unsupported')==capability,'Full original outcome totals')
    source_exit=77 if capability else 0
    m.require(val('mx_source_exit')==source_exit and exits==[(source_exit<<1)|1] and
              val('mx_done')==0x7365673134340001 and val('mx_errors')==val('mx_fatal')==0,'Actual terminal HTIF/source status')
    m.require(val('mx_words_checked')==comparisons==numerical*1024,'Exact executed full oracle count')
    for k in (0x180,0x305,0x302,0x303,0x304,0xc20,0xc21,8,15,3):
        if k in saved:m.require(csr.get(k)==saved[k],f'CSR restoration {k:x}')
    return dict(status='REFERENCE_FULL144_CAPABILITY_COMPLETE' if capability else 'REFERENCE_FULL144_NUMERICAL_PASS',
                commits=rows,firmware_commits=fw,firmware_before_parking=fw-parking,
                cases=144,helpers=helpercalls,capacity_calls=capacity,target_attempts=targets_seen,
                numerical=numerical,capability=capability,no_active=96,oracle_words=comparisons,
                oracle_bytes=comparisons*8,initialization_bytes=144*8192*4,predicate_bytes=144*128,
                checkpoints=checkpoint,traps=traps,outcomes=reports,htif=exits,source_exit=source_exit,
                initial_spill_evidence=store_guard.evidence,
                Linux_clone_COW_signal_equivalence=False,DUT_acceptance=False)
