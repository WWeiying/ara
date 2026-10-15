"""Independent parameterized oracle for the exact fourteen archived singles."""
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
UTIL=HERE.parent/'negative_stride_load_original01/observer.py'
_spec=importlib.util.spec_from_file_location('fof_frozen_memory_util',UTIL)
u=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(u)
require,readint,elf_bytes,disassemble,window=u.require,u.readint,u.elf_bytes,u.disassemble,u.window
MASK64=(1<<64)-1
VA=0x40000000
G=0xe370697ce370697c
DONE=0x666f6673696e6701
FIELDS={0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}
MEMBERS=tuple((sew,sc) for sew in (8,16,32) for sc in ((1,2,3,5) if sew==8 else (0,1,2,3,5)))
RESTORE=(0x300,0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3)

def spec_values(sew,scenario):
    require((sew,scenario) in MEMBERS,'Exact original fourteen-member scope')
    return dict(width=sew//8,vtype={8:0,16:8,32:16}[sew],base=VA+(4096-4*(sew//8) if scenario<3 else 4096),
                returned_vl=4 if scenario==0 else 8,mask=255 if scenario==0 else 15 if scenario in (1,2) else 0,
                checks=5477 if scenario==0 else 5481,
                checkpoint_checks=[2726,5463 if scenario==0 else 5467])

def output_value(sew,phase,i,scenario):
    spec_values(sew,scenario)
    if scenario<3 and phase==1:
        if scenario==0 and 5<=i<=8:return None
        if 1<=i<=4:return (11,48,85,122)[i-1]
    return 91

def pages(s,sew):
    p=s['fx_pages'];data=bytearray(20480)
    for i,value in enumerate((11,48,85,122)):
        off=4096-4*(sew//8)+i*(sew//8)
        data[off:off+sew//8]=value.to_bytes(sew//8,'little')
    for i,value in {1025:((p+12288)>>12<<10)|1,1026:0x200000cf,
                    1536:((p+16384)>>12<<10)|1,2048:(p>>12<<10)|0xc7}.items():
        data[i*8:i*8+8]=value.to_bytes(8,'little')
    return data

def expected(s,sew,phase,scenario):
    require(phase in (0,1),'Unknown phase');cfg=spec_values(sew,scenario);m={}
    def put(a,v,n=8):
        for j,b in enumerate(v.to_bytes(n,'little')):
            require(a+j not in m,'Overlapping expected objects');m[a+j]=b
    p=s['fx_pages'];require(p%4096==0 and s['fx_guard_lo']==p-64 and s['fx_guard_hi']==p+20480,'Backing-page guards')
    m.update({p+i:v for i,v in enumerate(pages(s,sew))})
    for name in ('fx_guard_lo','fx_guard_hi'):
        for i in range(8):put(s[name]+8*i,G)
    for i in range(130):
        v=output_value(sew,phase,i,scenario)
        if v is not None:put(s['fx_out']+i*cfg['width'],v,cfg['width'])
    for i in range(16):put(s['fx_mask']+i,spec_values(sew,scenario)['mask'] if i==0 else 0,1)
    satp=(8<<60)|((p+8192)>>12)
    for name,v in dict(fx_satp=satp,fx_count=phase,fx_marker=phase,fx_errors=0,fx_unexpected=0,
                       fx_return=cfg['returned_vl'] if phase else MASK64,fx_phase=phase).items():put(s[name],v)
    for i,v in enumerate([8,cfg['vtype'],0,117,5]):put(s['fx_post']+8*i,v if phase else MASK64)
    record=[9,s['fx_ecall'],0,0x800,satp,8,cfg['vtype'],0,117,5]
    for i,v in enumerate(record):
        if phase and i==3:continue
        put(s['fx_records']+8*i,v if phase else MASK64)
    return m

def compare(memory,s,sew,phase,scenario):
    gold=expected(s,sew,phase,scenario)
    for a,v in gold.items():require(a in memory and memory[a]==v,f'Phase{phase} byte0x{a:x} expected{v:02x} actual{memory.get(a)}')
    if phase:require(readint(memory,s['fx_records']+24)&0x8000031888==0x800,'Actual S-mode trap mstatus')
    return len(gold)

def host_check(text,sew,scenario):
    want=[]
    for phase in (0,1):
        for i in range(130):
            v=output_value(sew,phase,i,scenario)
            want.append(f'O {phase} {i} {int(v is not None)} {0x5b if v is None else v}')
    want += [f'M {i} {spec_values(sew,scenario)["mask"] if i==0 else 0}' for i in range(16)]
    raw=pages({'fx_pages':0x81000000},sew)
    want += [f'P {i} {int.from_bytes(raw[8*i:8*i+8],"little")}' for i in range(2560)]
    require(text.splitlines()==want,'Independent Host oracle discrepancy')
    return len(want)

def store_width(insn,regs,a):
    if insn&3!=3:
        d=u.decoder.decode(insn);require(d and d['kind']=='write','Unknown compressed store')
        require(a==(regs.get(d['base'],-1)+d['offset'])&MASK64,'Compressed store address')
        return d['size']
    if insn&127==0x23:
        imm=((insn>>25)<<5)|((insn>>7)&31);imm=imm-4096 if imm&2048 else imm
        require(a==(regs.get((insn>>15)&31,-1)+imm)&MASK64,'Scalar store address')
        return 1<<((insn>>12)&7)
    require(insn&127==0x27,'Unexpected memory write encoding')
    return {0:1,5:2,6:4,7:8}[(insn>>12)&7]

def completion_phase(started,pc,insn,width,value,s):
    if not started:
        require(pc==s['_start']+0x46 and insn==0x0002b023 and width==8 and value==0 and
                s['__bss_start']<=s['fx_completed'] and s['fx_completed']+8<=s['__bss_end'] and s['fx_completed']%8==0,
                'Only exact startup aligned sd-zero may initialize completion')
        return False
    require(value==DONE and width==8,'Final completion marker value/width')
    return True

LAST_CONTEXT={}

def trace_lines(path):
    LAST_CONTEXT.clear()
    with Path(path).open() as stream:
        for number,line in enumerate(stream,1):
            LAST_CONTEXT.update(raw_line=number,raw=line.rstrip()[:640])
            match=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)',line)
            if match:LAST_CONTEXT.update(event='spike_commit',pc=match[2],insn=match[3])
            yield line

def analyze(path,s,code,elf,sew,scenario):
    require((sew,scenario) in MEMBERS,"Exact original scenario")
    cfg=spec_values(sew,scenario);memory=elf_bytes(elf);regs={0:0};csr={};saved={}
    helper=window(code,s['load_0' if scenario in (1,3) else 'load_1'],11)
    unused=window(code,s['load_1' if scenario in (1,3) else 'load_0'],11);cap=window(code,s['capacity'],3)
    restore_pcs=[pc for pc,insn in code.items() if s['main']<=pc<s['fx_handler'] and insn&0xfe00707f==0x80007057]
    require(len(restore_pcs)==1,'Exactly one actual main vsetvl restore')
    restore_count=0
    step=0;capstep=0;actions=[];traps=[];points=[];targets=[];handler=[]
    count=0;firmware=0;checks=0;exits=[];park=0;started=False;restored=False;exit_pc=None
    for line in trace_lines(path):
        t=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
        if t:traps.append((t[1],int(t[2],16)))
        match=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
        if not match:continue
        mode,pc,insn,tail=int(match[1]),int(match[2],16),int(match[3],16),match[4];count+=1
        LAST_CONTEXT.update(row=count,checker_stage='reference_full_oracle',helper_step=step,capacity_step=capstep)
        if pc<0x80000000:
            require(not started,'Boot PC after firmware');continue
        firmware+=1
        require(code.get(pc)==insn,f'Actual retired PC/code0x{pc:x}')
        require(pc not in unused and pc not in (s['trap_entry'],s['replay_mismatch']),'Unused helper/default trap/oracle error')
        updates={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        access=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if exits:
            require(pc==exit_pc+4 and insn==0xa001 and not updates and not access and not re.search(r'\bc[0-9]+_',tail),'Only original post-HTIF parking allowed')
            park+=1;continue
        if insn&127 in (7,39,87):
            if pc in restore_pcs:
                require(len(points)==2 and restore_count==0,'Single final main vector restore');restore_count+=1
            else:require(pc in helper+cap,'Unexpected vector PC outside original helpers')
        if pc==s['main']:require(not started,'Main entered twice');started=True
        if 0<capstep<3:require(pc==cap[capstep],'Interrupted capacity window')
        if pc in cap:
            require(capstep<3 and pc==cap[capstep] and step==0,'Capacity window/order')
            if capstep==1:require(updates.get(10)==1024//sew,'Actual VLMAX')
            capstep+=1
        if pc==s['fx_enter_mret']:
            require(csr.get(0x300,0)&0x1800==0x800 and csr.get(0x180)==(8<<60)|((s['fx_pages']+8192)>>12) and csr.get(0x341)==s['fx_s_entry'],'Real S-mode/Sv39 entry')
            actions.append('enter_s')
        if 0<step<11:require(pc==helper[step],'Interrupted original11 helper window')
        if pc in helper:
            require(capstep==3 and step<11 and pc==helper[step] and mode==1,'Original helper exactly once/in S mode')
            if step==0:
                require([regs.get(i) for i in range(10,14)]==[cfg['base'],s['fx_out']+cfg['width'],s['fx_mask'],8],'Original four arguments')
                actions.append('helper')
            if step==3:
                require(csr.get(0xc20)==8 and csr.get(0xc21)==cfg['vtype'] and csr.get(8)==0,'Target vector CSRs')
                require(regs.get(10)==cfg['base'],'Target base')
                require(all(v is None for a,v in access),'Load unexpectedly writes memory')
                want=[cfg['base']+cfg['width']*i for i in range(4)] if scenario<3 else []
                require([a for a,v in access]==want,'Actual original active-only target read addresses')
                targets.append(dict(commit=firmware,pc=hex(pc),addresses=[hex(a) for a,v in access],raw_vector_commit=tail))
            if step==4:require(updates.get(10)==cfg['returned_vl'],'Immediate original returned VL')
            if step==5:require(updates.get(6)==0,'Immediate original returned vstart')
            if step==9:
                require([a for a,v in access]==[s['fx_out']+cfg['width']*(i+1) for i in range(8)] and all(v is not None for a,v in access),'Full original VL8 output store')
            step+=1
            if step==10:
                require(all(output_value(sew,1,i+1,scenario) is None or v==output_value(sew,1,i+1,scenario)
                            for i,(a,v) in enumerate(access)), 'All original defined output values')
        if pc==s['fx_younger_store']:require(mode==1 and step==11,'Younger marker ordering');actions.append('younger')
        if pc==s['fx_handler']:require(mode==3 and step==11 and not handler,'Unexpected/extra handler');handler.append({});actions.append('handler')
        if pc==s['fx_trap_mret']:
            require(len(handler)==1 and csr.get(0x341)==s['fx_m_resume'] and csr.get(0x300,0)&0x1800==0x1800,'Return to saved M-mode continuation');actions.append('return_m')
        if pc==s['check']:require(regs.get(10)==regs.get(11),'Actual scalar comparison failure');checks+=1
        if pc==s['fx_checkpoint']:
            phase=readint(memory,s['fx_phase']);require(phase==len(points),'Checkpoint order')
            amount=compare(memory,s,sew,phase,scenario)
            require(checks==readint(memory,s['fx_checks'])==cfg['checkpoint_checks'][phase],'Full checkpoint scalar-count')
            if phase:
                require(len(handler)==1 and handler[0]=={i:readint(memory,s['fx_records']+8*i) for i in range(10)},'Actual handler CSR reads vs memory record')
            points.append(dict(phase=phase,bytes=amount,checks=checks,commit=firmware));actions.append('checkpoint'+str(phase))
        if insn&127==0x73 and (insn>>12)&7==2 and (insn>>15)&31==0 and (insn>>7)&31 in updates:
            k=insn>>20;v=updates[(insn>>7)&31]
            if started and capstep==0 and k in RESTORE and k not in saved:saved[k]=v
            if s['fx_trap']<=pc<s['main'] and k in FIELDS:
                require(handler and FIELDS[k] not in handler[-1],'Handler CSR ownership');handler[-1][FIELDS[k]]=v
        for a,v in access:
            if v is None:continue
            width=store_width(insn,regs,a);require(width in (1,2,4,8),'Unexpected write width')
            require(not VA<=a<VA+8192,'Source load fixture never writes virtual data mapping')
            for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):memory[a+i]=b
            if a==s['tohost']:
                require(width==8 and v==1 and started,'Actual numeric HTIF success');exits.append(v);exit_pc=pc
            if a==s['fx_completed'] and completion_phase(started,pc,insn,width,v,s):
                require(set(saved)==set(RESTORE),'Complete saved CSR set')
                for k,v0 in saved.items():require(csr.get(k)==v0,f'Actual restored CSR0x{k:x}')
                restored=True
        regs.update(updates);regs[0]=0
        csr.update({int(k):int(v,16) for k,v in re.findall(r'\bc([0-9]+)_[^\s]+\s+0x([0-9a-f]+)',tail)})
        if insn&127==0x73 and (insn>>12)&7==2 and (insn>>15)&31==0 and (insn>>7)&31 in updates:csr[insn>>20]=updates[(insn>>7)&31]
    require(traps==[('trap_supervisor_ecall',s['fx_ecall'])],'Exact no-target-fault trap ledger')
    require(actions==['checkpoint0','enter_s','helper','younger','handler','return_m','checkpoint1'],'Exact action order')
    require(len(targets)==1 and step==11 and capstep==3 and restored and restore_count==1,'Complete target/helper/capacity/restore')
    require(checks==readint(memory,s['fx_checks'])==cfg['checks'],'Complete scalar oracle')
    require(exits==[1] and readint(memory,s['fx_completed'])==DONE and count<=800000,'Reference terminal/bound')
    n=readint(memory,s['replay_log_count']);require(n==len(b'SMALL_EXCEPTIONS_14_PASS\n'),'Console length')
    require(bytes(memory.get(s['replay_log']+i,256) for i in range(n))==b'SMALL_EXCEPTIONS_14_PASS\n','Exact raw oracle marker')
    return dict(status='REFERENCE_CHECKER_PASS_NOT_DUT',commits=count,firmware_commits=firmware,
                sew=sew,scenario=scenario,boot_commits=count-firmware,firmware_to_htif=firmware-park,
                scalar_checks=checks,checkpoints=points,actions=actions,targets=targets,traps=traps,
                actual_handler_csrs=handler,original_helper_instructions=11,helper_entries=1,capacity_instructions=3,
                target_attempts=1,output_allocation_elements=130,output_checked_elements=126 if scenario==0 else 130,
                original_result_elements=4 if scenario==0 else 8,original_guards=[0,9],mask_bytes=16,
                allowed_undefined_output_indices=[5,6,7,8] if scenario==0 else [],
                full_data_bytes=8192,page_table_bytes=12288,htif=exits,postexit_park=park,
                linux_signal_equivalence=False,parent8_ELFs_accepted=False)
