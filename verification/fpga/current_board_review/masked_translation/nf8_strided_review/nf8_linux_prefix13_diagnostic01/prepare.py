#!/usr/bin/env python3
"""Build only one modified Linux diagnostic; no board, kernel or VCS launch."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
TOOLS=Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
CAMP=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
IDENT=CAMP/'rvv_fault_identity_regression57/source_mf2_False_0_nf8_stridedTrue_reverseFalse'
NAME='rvv_fault_replay_segment_nf8_strided_e32_mf2'
CC=Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')
OBJDUMP=CC.with_name(CC.name.replace('gcc','objdump'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def require(ok,why):
    if not ok:raise ValueError(why)
def command(cmd,log):
    save(log.with_suffix('.command.json'),list(map(str,cmd)))
    with log.open('x') as f:r=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT,timeout=60)
    require(r.returncode==0,str(log))
def rewrite(source):
    def one(a,b):
        nonlocal source
        require(source.count(a)==1,'Unique source boundary '+a[:70]);source=source.replace(a,b)
    one('extern char fault_0_pc[],fault_1_pc[];','extern char fault_0_pc[],fault_1_pc[];\n#include "diagnostic.h"')
    one('static void text(const char *s){long n=0;',
        'static void text(const char *s){if(diag_in_handler){if(diag_trial<DIAG_CASES && !diagnostics[diag_trial].fatal_message)diagnostics[diag_trial].fatal_message=s;return;}long n=0;')
    one('static void handler(int sig,siginfo_t *info,void *context){',
        'static void handler(int sig,siginfo_t *info,void *context){\n    diag_in_handler=1;diag_signal(sig,info,(const struct ucontext *)context);')
    one('    if(!state || state->vlenb', '    diag_state(state);\n    if(!state || state->vlenb')
    one('    unsigned address_matches=0;', '    diagnostics[diag_trial].frame_valid=1;\n    unsigned address_matches=0;')
    end='state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE))++handler_errors;'
    one(end,end.replace('++handler_errors;','''{
        ++handler_errors;
        if(sig!=SIGSEGV)diag_error(E_SIGNAL,0,0,sig,SIGSEGV);
        else if(!address_matches)diag_error(E_ADDRESS,0,0,(uintptr_t)info->si_addr,expected_address);
        else if(info->si_code!=(unmapped ? SEGV_MAPERR:SEGV_ACCERR))diag_error(E_CODE,0,0,info->si_code,unmapped ? SEGV_MAPERR:SEGV_ACCERR);
        else if(uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc))diag_error(E_PC,0,0,uc->uc_mcontext.sc_regs.pc,(uintptr_t)(store_case ? fault_1_pc:fault_0_pc));
        else if(state->vstart!=expected_start)diag_error(E_VSTART,0,0,state->vstart,expected_start);
        else if(state->vl!=REPLAY_ELEMENTS)diag_error(E_VL,0,0,state->vl,REPLAY_ELEMENTS);
        else diag_error(E_VTYPE,0,0,state->vtype,((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE));
    }'''))
    for old,new in [
        ('if(saved[i]!=input[f*cap+i])++handler_errors;', 'if(saved[i]!=input[f*cap+i]){++handler_errors;diag_error(E_SAVED,f,i,saved[i],input[f*cap+i]);}'),
        ('if(active(i) && *(word *)field_address(i,f)!=input[f*cap+i])++handler_errors;', 'if(active(i) && *(word *)field_address(i,f)!=input[f*cap+i]){++handler_errors;diag_error(E_PREFIX_MEMORY,f,i,*(word *)field_address(i,f),input[f*cap+i]);}'),
        ('else if(saved[i]!=(active(i) ? original(field_address(i,f)):(word)0x5b))++handler_errors;', 'else if(saved[i]!=(active(i) ? original(field_address(i,f)):(word)0x5b)){++handler_errors;diag_error(E_SAVED,f,i,saved[i],active(i) ? original(field_address(i,f)):(word)0x5b);}'),
        ('#if NEGATIVE_SKIP\n    state->vstart=REPLAY_ELEMENTS;\n#endif\n}', '#if NEGATIVE_SKIP\n    state->vstart=REPLAY_ELEMENTS;\n#endif\n    diag_in_handler=0;\n}'),
        ('        long address=call(222,0,8192,3,0x22,-1,0);', '''        diag_trial=cases;
        volatile struct diag_record *d=&diagnostics[cases];
        d->trial=cases;d->unmapped=unmapped;d->store=store_case;d->boundary=boundary;
        d->mode=mode;d->gap=gap;d->split=split;d->phase=D_SETUP;
        unsigned prior_errors=errors;
        long address=call(222,0,8192,3,0x22,-1,0);'''),
        ('        if(call(unmapped ? 215:226,PROTECTED_PAGE,4096,0,0,0,0)){', '''        d->map=mapping;d->base=target;d->expected_addr=expected_address;d->expected_start=expected_start;d->phase=D_PROTECT;
        if(call(unmapped ? 215:226,PROTECTED_PAGE,4096,0,0,0,0)){'''),
        ('        unsigned long status=(store_case ? replay_1:replay_0)', '        d->phase=D_HELPER;\n        unsigned long status=(store_case ? replay_1:replay_0)'),
        ('        if(status || faults!=(expected_start<REPLAY_ELEMENTS))++errors;', '''        d->phase=D_RETURN;
        if(status || faults!=(expected_start<REPLAY_ELEMENTS)){
            ++errors;
            if(status)diag_error(E_RETURN,0,0,status,0);
            else diag_error(E_FAULTS,0,0,faults,expected_start<REPLAY_ELEMENTS);
        }'''),
        ('        if(!faults)restore_page();', '        if(!faults)restore_page();\n        d->phase=D_OUTPUT;'),
        ('            if(output[f*cap+i+1]!=wanted)++errors;', '            if(output[f*cap+i+1]!=wanted){++errors;diag_error(E_OUTPUT,f,i,output[f*cap+i+1],wanted);}'),
        ('        for(unsigned i=0;i<8192/sizeof(word);++i){', '        d->phase=D_MEMORY;\n        for(unsigned i=0;i<8192/sizeof(word);++i){'),
        ('            if(((word *)mapping)[i]!=wanted)++errors;', '            if(((word *)mapping)[i]!=wanted){++errors;diag_error(E_MEMORY,f,i,((word *)mapping)[i],wanted);}'),
        ('        if(output[0]!=(word)0x5b || output[cap*REPLAY_FIELDS+1]!=(word)0x5b)++errors;', '''        d->phase=D_GUARD;
        if(output[0]!=(word)0x5b || output[cap*REPLAY_FIELDS+1]!=(word)0x5b){
            ++errors;unsigned gi=output[0]!=(word)0x5b ? 0:cap*REPLAY_FIELDS+1;
            diag_error(E_GUARD,0,gi,output[gi],(word)0x5b);
        }'''),
        ('        call(215,mapping,8192,0,0,0,0);++cases;', '''        d->signal_count=faults;d->handler_error_count=handler_errors;d->error_delta=errors-prior_errors;
        d->phase=D_UNMAP;
        call(215,mapping,8192,0,0,0,0);++cases;
        d->phase=D_DONE;d->complete=1;
        if(cases==DIAG_CASES)goto prefix_done;'''),
        ('    text(errors ? "RVV_FAULT_REPLAY_FAIL sew=":"RVV_FAULT_REPLAY_PASS sew=");', 'prefix_done:\n    diag_emit(cases);\n    text(errors ? "RVV_FAULT_REPLAY_FAIL sew=":"RVV_FAULT_REPLAY_PASS sew=");')]:one(old,new)
    return source
def instruction_list(elf):
    text=subprocess.check_output([str(OBJDUMP),'-d',str(elf)],text=True)
    return [(int(m[1],16),m[2],m[3]) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.*)',text,re.M)],text
def main():
    out=HERE/'build03';require(not out.exists(),'Fresh diagnostic build only');out.mkdir()
    manifest=json.loads((IDENT/'manifest.json').read_text());pins={}
    def pin(p,want=None):
        actual=sha(p);require(want is None or actual==want,'Identity drift '+str(p));pins[str(p)]=actual
    for n,h in manifest['source_sha256'].items():pin(TOOLS/n,h)
    pin(IDENT/'manifest.json','c6d474560aad244cfbee36870bcc440067c6d849e0a268753a4a0e07d3472bb2')
    old=IDENT/'overlay/opt/ara-tests'/NAME;pin(old,'c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282')
    assembly=IDENT/(NAME+'.S');pin(assembly,'63c68bc8c2c935884520082cd423c51e9f14fb7caac7a42816026b9597acb8db')
    # Importing the generator does not invoke its build/run entry.
    spec=importlib.util.spec_from_file_location('original_fault_generator',TOOLS/'fault_replay.py');generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    require(generator.assembly(32,False,None,'mf2',8,True)==assembly.read_text(),'Generator assembly identity')
    shutil.copyfile(TOOLS/'fault_replay_oracle.c',out/'original.c');shutil.copyfile(assembly,out/'scenario.S')
    original=(out/'original.c').read_text();modified=rewrite(original);(out/'diagnostic.c').write_text(modified)
    (out/'source.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),fromfile='identity57/original.c',tofile='diagnostic.c')))
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wall','-Wextra','-Werror']
    defs=['-DSEW=32','-DTRACE_REPLAY=0','-DNEGATIVE_RESTART=0','-DINDEXED_REPLAY=0','-DINDEX_SEW=32','-DLMUL_NUM=1','-DLMUL_DEN=2','-DLMUL_CODE=7','-DREPLAY_FIELDS=8','-DSTRIDED_REPLAY=1']
    command([CC,*flags,'-Wl,-s',*defs,out/'original.c',out/'scenario.S','-o',out/'original_rebuilt.elf'],out/'original_compile.log')
    require(sha(out/'original_rebuilt.elf')==sha(old),'Original Linux ELF byte identity')
    elf=out/'nf8_linux_prefix13_diagnostic.elf'
    command([CC,*flags,*defs,'-I'+str(HERE),out/'diagnostic.c',out/'scenario.S','-o',elf],out/'diagnostic_compile.log')
    oldrows,_=instruction_list(old);newrows,dis=instruction_list(elf);(out/'diagnostic.dis').write_text(dis)
    nm=subprocess.check_output([str(CC.with_name(CC.name.replace('gcc','nm'))),'-n',str(elf)],text=True);(out/'symbols.txt').write_text(nm)
    syms={m[3]:int(m[1],16) for l in nm.splitlines() if (m:=re.match(r'^(\w+)\s+(\w)\s+(.+)$',l))}
    bounds=[('capacity',syms['capacity'],syms['replay_0']),('replay_0',syms['replay_0'],syms['replay_1']),('replay_1',syms['replay_1'],None)]
    identity={}
    for n,lo,hi in bounds:
        rows=[r for r in newrows if r[0]>=lo and (hi is None or r[0]<hi)]
        if hi is None:rows=rows[:next(i for i,r in enumerate(rows) if r[2]=='ret')+1]
        codes=[r[1] for r in rows];matches=[i for i in range(len(oldrows)-len(rows)+1) if [r[1] for r in oldrows[i:i+len(rows)]]==codes]
        require(len(matches)==1,'Unique unchanged original helper bytes '+n)
        identity[n]=dict(original_pc=hex(oldrows[matches[0]][0]),diagnostic_pc=hex(lo),instructions=len(rows),codes=codes,identical=True)
    # The original compiler uses RVV for the sigaction struct copy. Preserve it.
    def vector(c):return c&127==87 or c&127 in (7,39) and (c>>12)&7 in (0,5,6,7)
    oldvectors=[c for _,c,_ in oldrows if len(c)==8 and vector(int(c,16))]
    newvectors=[c for _,c,_ in newrows if len(c)==8 and vector(int(c,16))]
    require(oldvectors==newvectors,'Changed original vector instruction sequence')
    bootstrap=[dict(pc=hex(pc),code=c,disassembly=d) for pc,c,d in newrows
               if pc<syms['capacity'] and len(c)==8 and vector(int(c,16))]
    require(len(bootstrap)==3 and all(int(r['pc'],16)>=syms['probe_main'] for r in bootstrap),
            'Only original main bootstrap may use RVV outside helpers')
    for p in [CC.resolve(),OBJDUMP,HERE/'diagnostic.h',Path(__file__)]:pin(p)
    save(out/'proof.json',dict(status='COMPILED_MODIFIED_LINUX_DIAGNOSTIC_NOT_RUN',original_elf=str(old),original_sha256=sha(old),original_rebuild_byte_identical=True,
        diagnostic_elf=str(elf),diagnostic_sha256=sha(elf),diagnostic_is_original_byte_identical=False,helper_identity=identity,
        original_vector_sequence_identical=True,original_bootstrap_rvv=bootstrap,
        symbols={n:hex(syms[n]) for n in ('fault_0_pc','fault_1_pc','diagnostics','diag_trial','diag_in_handler')},
        calls=13,natural_trials=list(range(13)),last_tuple=dict(unmapped=0,store=0,boundary=1,mode=3,gap=1,split=0),
        expected_summary=dict(cases=13,signals=12,errors=0),pins=pins))
    for p,h in pins.items():require(sha(Path(p))==h,'Post-build drift')
    print('COMPILED_MODIFIED_LINUX_DIAGNOSTIC_NOT_RUN',sha(elf))
if __name__=='__main__':main()
