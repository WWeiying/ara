"""Independent byte-memory, target/retry and original-helper reference checks."""
import json
from pathlib import Path
import re
import subprocess
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'masked_translation'))
import sv39_adapter as base

def require(ok,msg):
    if not ok: raise ValueError(msg)

def value(i):
    return ((((i*13+7)%32)*1024*7919)^0xa5a50f0f)&0xffffffff

def check_point(actual,r):
    expected=[32,17,0,117,5]+[value(i) if r<50 or 7<=i<17 and i%2 else 0xfffffff9 for i in range(32)]+[0x5b12]*2
    require(actual==expected,'Independent results / CSR / guards mismatch round '+str(r))

def check_terminal(exits,errors,exit_code,done,log,marker):
    require(exits==[1] and errors==0 and exit_code==0,'Firmware exit/errors failed')
    require(done==0x525656303146494e,'Missing final magic')
    require(log==marker+'\nINDEXED_ORIGINAL_PASS\n','Missing/contradictory raw pass markers: '+log)

def validate(work,case):
    s=json.loads((work/'spike.symbols.json').read_text())
    fault,overlap=case['fault'],case['overlap']
    host=(work/'host.stdout').read_text().splitlines()
    wanted=['HOST_VALUE %d %d %08x'%(r,i,value(i)) for r in range(50) for i in range(32)]
    if not fault: wanted+=['HOST_MASK %d %08x'%(i,value(i) if 7<=i<17 and i%2 else 0xfffffff9) for i in range(32)]
    marker='VECTOR_PASS loops=50 overlap=%d data_bits=32 index_bits=64 fault_pages='%overlap
    marker+= '1 minor_faults=1600' if fault else '0 mask_tail_vstart=checked'
    require(host==wanted+[marker],'Host original full oracle / independent Python mismatch')
    memory={}; regs={0:0}; commits=0; exits=[]; points=[]; targets=[]; faults=[]; reloads=0
    pending=None; repairs=0; retried=0
    def read(a,n=8): return int.from_bytes(bytes(memory.get(a+i,0) for i in range(n)),'little')
    def readname(n): return read(s[n])
    with (work/'spike.trace').open() as trace:
        for line in trace:
            if 'exception trap_load_page_fault' in line:
                m=re.search(r'epc 0x([0-9a-f]+)',line); faults.append(int(m[1],16))
            elif 'exception ' in line:
                require('trap_supervisor_ecall' in line,'Unexpected trap '+line.strip())
            m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m: continue
            mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]; commits+=1
            require(pc!=s['trap_entry'],'Default runtime trap')
            if insn==0x02057207:
                require(mode==1 and pending is None,'Index reload during pending fault retry')
                reloads+=1
            if insn in (0x0645f207,0x0645f807,0x0445f807):
                require(mode==1,'Target outside S-mode')
                if pending is not None:
                    require(pc==pending,'Retry moved target PC'); pending=None; retried+=1
                targets.append((pc,insn))
            if pc==s['io_repair_sfence']:
                require(mode==3,'PTE repair not M mode')
                repairs+=1; pending=readname('io_target_pc')
            if pc==s['io_checkpoint']:
                r=readname('io_round')
                require(r==len(points),'Round count/oracle checkpoint mismatch')
                actual=[read(s['io_result']+r*39*8+i*8) for i in range(39)]
                check_point(actual,r)
                points.append(dict(round=r,commit=commits,values_checked=32))
            for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail):
                if not v: continue
                a,v=int(a,16),int(v,16)
                if insn&3!=3:
                    d=base.compressed_memory(insn)
                    require(d and d['kind']=='write','Unknown compressed store')
                    width=d['size']
                else:
                    opcode,funct=insn&127,(insn>>12)&7
                    require(opcode in (0x23,0x27),'Unrecognized memory-write instruction')
                    width=1<<funct if opcode==0x23 else {0:1,5:2,6:4,7:8}[funct]
                require(not 0x40000000<=a<0x40020000,'Write to read-only source mapping')
                for i in range(width): memory[a+i]=(v>>(i*8))&255
                if a==s['tohost']: exits.append(v)
            regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    require(len(points)==(50 if fault else 51),'Incomplete 50-round oracle')
    require(reloads==(50 if fault else 51),'Wrong index setup count')
    expected_pc=s['overlap'] if overlap else s['gather32']+26
    require(len(targets)==(1650 if fault else 51),'Wrong target attempts')
    if fault:
        require(faults==[expected_pc]*1600 and repairs==1600 and retried==1600 and pending is None,'Fault/repair/retry ledger differs')
        for r in range(50):
            require(read(s['io_fault_count']+8*r)==32,'Fault count changed')
            for n in range(32):
                got=[read(s['io_records']+((r*32+n)*7+j)*8) for j in range(7)]
                require(got==[expected_pc,0x40000000+((n*13+7)%32)*4096,n,32,17,117,5],'Trap record/CSR mismatch')
    else: require(not faults and repairs==0,'Resident page fault')
    for i in range(32768): require(read(s['pages']+i*4,4)==((i*7919)^0xa5a50f0f)&0xffffffff,'Source memory modified')
    log=bytes(memory.get(s['replay_log']+i,0) for i in range(readname('replay_log_count'))).decode()
    check_terminal(exits,readname('io_errors'),readname('io_exit_code'),readname('io_done'),log,marker)
    # Compare unchanged helper machine-code sequence against the byte-identical original ELF.
    dis=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-objdump')),'-d',str(work/'original.elf')],text=True)
    def instructions(text): return [(int(a,16),op) for a,op in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',text,re.M)]
    old=instructions(dis); new=instructions((work/'spike.dis').read_text())
    start=next(i for i in range(len(old)-1) if old[i][1]=='02000293' and old[i+1][1]=='0da2f357')
    original=[op for _,op in old[start:]]
    adapter=[op for a,op in new if a>=s['gather32']][:len(original)]
    require(original==adapter,'Original helper opcode sequence changed')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',commits=commits,points=points,original_helper_instructions=len(original),
        original_elf_sha256=base.sha(work/'original.elf'),soc_elf_sha256=base.sha(work/'soc.elf'),spike_elf_sha256=base.sha(work/'spike.elf'),
        reloads=reloads,targets=len(targets),faults=len(faults),repairs=repairs,retries=retried,checks=readname('io_checks'),
        raw_markers=log,policy='32 initially invalid read-only pages per round; Linux batching unknown',VCS_launched=False)
