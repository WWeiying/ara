"""One reviewed candidate: Host equivalence/negatives and fixed RV64 builds only."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
A=HERE.parents[1]
SOURCE=A/'full_e32_m4_integrated_source_proposal01'
MODEL=A/'full_e32_m4_source_model01/generated01'
ARCH=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
RUNTIME=A/'full_e16_mf4_prepare01/runtime'

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
    with Path(p).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def emit(p,s):
    with Path(p).open('x') as f:f.write(s)
def replace(s,a,b,count=1):
    require(s.count(a)==count,'Exact source transform '+a[:80]);return s.replace(a,b)
def run(command,log,expected=0,limit=90):
    command=list(map(str,command));save(str(log)+'.command.json',dict(command=command,timeout_seconds=limit))
    print('START '+str(log.relative_to(HERE)),flush=True);begin=time.monotonic();rc=None;timeout=False
    with log.open('x') as out:
        try:rc=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,timeout=limit).returncode
        except subprocess.TimeoutExpired:timeout=True
    receipt=dict(returncode=rc,expected_returncode=expected,timed_out=timeout,elapsed_seconds=time.monotonic()-begin)
    save(str(log)+'.exit.json',receipt);print('END '+str(log.relative_to(HERE))+' '+json.dumps(receipt),flush=True)
    require(type(rc) is int and rc==expected and not timeout,'Actual child failure '+str(log))
    return receipt

def packed_host(s):
    s=replace(s,'    __builtin_memcpy(&value, p, 8);\n    __asm__ volatile',
      '    if(running && fault==32 && p==actual_base+16)return UINT64_C(0x0000005b0000005b);\n    __builtin_memcpy(&value, p, 8);\n    __asm__ volatile')
    s=replace(s,'    return value;\n}\n\nstatic __attribute__((always_inline)) inline uint64_t',
      '    actual_event(p,value);\n    return value;\n}\n\nstatic __attribute__((always_inline)) inline uint64_t')
    s=replace(s,'    __builtin_memcpy(&value, p, 8);\n    return value;',
      '    __builtin_memcpy(&value, p, 8);\n    if(running && fault==27)value^=1;\n    gold_event(p,value);\n    return value;')
    for off in range(0,520,8):
        statement=f'    __builtin_memcpy(p + {off}, &sentinel, 8);'
        s=replace(s,statement,f'    if(!(running && fault==35 && calls==1 && {off}==8))'+'{'+statement.strip()+f'init_event({off},p);'+'}')
    s=replace(s,'    tag = (ID); \\',
      '    tag = (ID); if(running && fault==28)tag^=1; tag_event(tag,(ID)); \\')
    s=replace(s,'    const uint16_t id = ids[(INDEX)]; \\',
      '    const uint16_t id = ids[(INDEX)]; id_event((INDEX),id); \\')
    s=replace(s,'    if (id != tag) E32M4_CACHE_FILL(id); \\',
      '    if ((id != tag && !(running && fault==30)) || (running && fault==31)) E32M4_CACHE_FILL(id); \\')
    s=replace(s,'    uint64_t c0, c1, c2, c3, c4, c5, c6, c7;',
      '    uint64_t c0=UINT64_C(0x5b0000005b),c1=c0,c2=c0,c3=c0,c4=c0,c5=c0,c6=c0,c7=c0;')
    s=replace(s,'    uint16_t tag;','    uint16_t tag=0;')
    s=replace(s,'    const uint16_t first_id = ids[0];',
      '    cache_begin(out,ids);\n    const uint16_t first_id = ids[0]; id_event(0,first_id);')
    s=replace(s,'    E32M4_CACHE_FILL(first_id);',
      '    if(!(running && fault==29 && calls==2)) E32M4_CACHE_FILL(first_id);')
    s=replace(s,'    E32M4_COMPARE_BLOCK(0);',
      '    E32M4_COMPARE_BLOCK(0);\n    if(running && fault==33 && mismatch){cache_end();return mismatch;}')
    s=replace(s,'    const uint16_t last_id = ids[8];','    const uint16_t last_id = ids[8]; id_event(8,last_id);')
    return replace(s,'    return mismatch;','    cache_end();\n    return mismatch;')

def make_host(directory,packed,rows,seeds):
    directory.mkdir()
    case=(HERE/'case.c' if packed else A/'recovery22/reconstructed_oracle.c').read_text()
    if packed:
        case=replace(case,'#include "../full_e32_m4_mask_constant_source_proposal01/mask_constant.h"','#include "mask_constant.h"')
        fp=(HERE/'fp_period.h').read_text()
        fp=replace(fp,'    __builtin_memcpy(dst, &value, 4);',
          '    if(running && ((fault==20 && calls==1366 && dst==a+127)||(fault==21 && calls==1366 && dst==b+127)))return;\n'
          '    if(running && fault==22 && dst==a)dst=b;\n    __builtin_memcpy(dst, &value, 4); fp_event(dst,value);')
        # Header is before the actual buffer definitions; explicit host-only forward declarations.
        fp='static uint32_t a[1024],b[1024];\n'+fp
        for i in range(8):fp=replace(fp,f'    const uint32_t v{i} = table[{i}];',f'    const uint32_t v{i} = table[{i}]; if(!(running && fault==34 && {i}==7))input_event({i},v{i});')
        emit(directory/'fp_period.h',fp)
        mask=(HERE/'mask_constant.h').read_text()
        mask=replace(mask,'    bytes[(OFFSET)] = (uint8_t)(VALUE); \\',
          '    if(running && fault==24 && calls==0 && mask_pos==16 && !injected) { injected=1; } else { unsigned host_offset=(OFFSET); if(running && fault==25 && mask_pos==16)host_offset^=1; bytes[host_offset]=(uint8_t)(VALUE); selected_event(host_offset,bytes[host_offset]); } \\')
        mask=replace(mask,'    __builtin_memcpy(mask + (OFFSET), &zero, 8); \\',
          '    if(!(running && ((fault==23 && calls==3 && (OFFSET)==120)||(fault==26 && calls==0)))) { __builtin_memcpy(mask + (OFFSET), &zero, 8); clear_event((OFFSET),mask); } \\')
        emit(directory/'mask_constant.h',mask)
    else:
        case=replace(case,'#include "operations.h"',f'#include "{ARCH}/e32/operations.h"')
        lo=case.index('static long syscall3(');hi=case.index('static void text(',lo)
        case=case[:lo]+'extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n'+case[hi:]
        case=replace(case,'static void finish(long code) {\n    syscall3(94,code,0,0);for(;;){}\n}\n','')
        case=replace(case,'void probe_main(void) {','int arithmetic_main(void) {')
        case=replace(case,'finish(2);','return 2;')
        case=replace(case,'finish(errors ? 1:0);','return errors ? 1:0;')
        case=case[:case.index('__asm__(".global _start')]
        case=replace(case,'for(unsigned i=0;i<128;++i)mask[i]=0;',
          'for(unsigned i=0;i<128;++i){mask[i]=0;if(i%8==7)clear_event(i-7,mask);}')
        case=replace(case,'if(selected(mode,i))mask[i/8]|=1u<<(i%8);',
          'if(selected(mode,i)){mask[i/8]|=1u<<(i%8);selected_event(i/8,mask[i/8]);}')
        for bank in ('a','b'):
            stmt='a[i]=fp_inputs[(i+seed)%8];' if bank=='a' else 'b[i]=fp_inputs[(i*3+seed)%8];'
            case=replace(case,stmt,stmt+f'fp_event({bank}+i,{bank}[i]);')
        case=replace(case,'for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;',
          'for(unsigned i=0;i<cap+2;++i){out[i]=sentinel;init_event(4*i,out);}')
    emit(directory/'host_case.c',case)
    emit(directory/'packed_cache.h',packed_host((HERE/'packed_cache.h').read_text()))
    emit(directory/'host.c',(HERE/'host.c').read_text())
    fixture='struct row{unsigned seed,op,vl,mode,si,start;};\nstatic const struct row fixture[5985]={\n'
    fixture+=',\n'.join('{'+','.join(str(r[k]) for k in ('seed','op','vl','mode','trial','start'))+'}' for r in rows)+'\n};\n'
    for bank in ('a','b'):
        fixture+=f'static const uint32_t seed_{bank}[3][128]={{\n'+',\n'.join('{'+','.join(f'UINT32_C({v})' for v in r[bank])+'}' for r in seeds)+'\n};\n'
    emit(directory/'fixture.h',fixture)

def disassemble(elf,root):
    run([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],root/'program.dis')
    run([CC.with_name('riscv64-unknown-elf-nm'),'-n',elf],root/'program.nm')
    symbols={};code={};functions={};current=None
    for line in (root/'program.nm').read_text().splitlines():
        m=re.match(r'^([0-9a-f]+)\s+\w\s+(\S+)$',line)
        if m:symbols[m[2]]=int(m[1],16)
    for line in (root/'program.dis').read_text().splitlines():
        label=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if label:current=label[2];functions[current]=[]
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\s]+)\s*(.*)',line)
        if m:
            pc=int(m[1],16);entry=dict(pc=pc,insn=int(m[2],16),op=m[3],args=m[4].strip());code[pc]=entry
            if current:functions[current].append(entry)
    save(root/'symbols.json',symbols);save(root/'functions.json',functions)
    return symbols,code,functions

def main():
    begin=time.monotonic()
    review=A/'full_e32_m4_static_review01/INTEGRATED_SOURCE_FINAL.json'
    require(sha(review)=='041039e5e0d72f9944f142b466b04d57bd30de7380ccbe8d378d55f68a6c8dae','Exact independent source review')
    pins=json.loads((SOURCE/'STATIC_BINDING.json').read_text())['pins']
    for p,h in pins.items():require(sha(p)==h,'Reviewed pin drift '+p)
    for p in [review,SOURCE/'STATIC_BINDING.json',SOURCE/'COST_VL_ADDENDUM01.md',HERE/'prepare.py',HERE/'host.c',
              CC,CC.with_name('riscv64-unknown-elf-objdump'),CC.with_name('riscv64-unknown-elf-nm'),Path('/usr/bin/cc').resolve(),
              *[RUNTIME/n for n in ('startup.S','runtime.c','replay.ld')]]:pins[str(p)]=sha(p)
    save(HERE/'preflight.json',dict(status='AUTHORIZED_SINGLE_CANDIDATE_HOST_COMPILE_ONLY',pins=pins))
    for name in ('case.c','fp_period.h','packed_cache.h','gold_data.S'):emit(HERE/name,(SOURCE/name).read_text())
    emit(HERE/'mask_constant.h',(A/'full_e32_m4_mask_constant_source_proposal01/mask_constant.h').read_text())
    # Only a relocation of the reviewed include: its exact header remains byte-identical.
    case=(HERE/'case.c').read_text()
    require('../full_e32_m4_mask_constant_source_proposal01/mask_constant.h' in case,'Original include identity')
    # Preserve case.c bytes and provide the same relative include path via a source search directory.
    rows=json.loads((MODEL/'calls.json').read_text());seeds=json.loads((MODEL/'seed_inputs.json').read_text())
    host=[]
    for packed in (False,True):
        root=HERE/('host_packed' if packed else 'host_original');make_host(root,packed,rows,seeds)
        flags=['-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DSEW=32']
        if packed:flags+=['-DPACKED_CASE=1']
        run(['/usr/bin/cc',*flags,root/'host.c',HERE/'gold_data.S','-o',root/'host'],root/'compile.log')
        for mutation in list(range(15))+(list(range(20,36)) if packed else []):
            expected=90 if mutation>=20 else int(mutation!=0)
            log=root/f'case{mutation}.log';receipt=run([root/'host',mutation,MODEL/'gold_u32le.bin'],log,expected)
            if expected==90:require('HOST_BLOCK' in log.read_text(),'Structural negative veto')
            else:require('HOST_FULL5985 results=766080 guards=11970' in log.read_text(),'Full original Host scope')
            host.append(dict(packed=packed,mutation=mutation,log=str(log),sha256=sha(log),**receipt))
    for n in range(15):require((HERE/'host_original'/f'case{n}.log').read_bytes()==(HERE/'host_packed'/f'case{n}.log').read_bytes(),'Exact original/candidate full fallback transcript')
    save(HERE/'host_result.json',dict(status='HOST_FULL5985_EQUIVALENT_UB_NEGATIVES_PASS_NOT_RV64',runs=host,source_runtime_distinction=True))
    original=HERE/'original_disassembly';original.mkdir()
    _,_,original_functions=disassemble(ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m4',original)
    backend_proof={}
    for backend in ('soc','spike'):
        root=HERE/backend;root.mkdir();emit(root/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        elf=root/'program.elf'
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin','-fno-stack-protector',
               '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0','-ffunction-sections','-fdata-sections',
               '-Wall','-Wextra','-Werror','-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections',
               '-Wl,-Map='+str(root/'program.map'),'-T',RUNTIME/'replay.ld','-DSEW=32','-I'+str(SOURCE)]
        if backend=='spike':flags+=['-DSPIKE_REFERENCE=1']
        receipt=run([CC,*flags,HERE/'case.c',HERE/'gold_data.S',ARCH/'rvv_matrix_e32_m4.S',root/'main.c',RUNTIME/'startup.S',RUNTIME/'runtime.c','-lgcc','-o',elf],root/'compile.log')
        symbols,code,functions=disassemble(elf,root)
        helpers=['capacity']+[f'op_{i}' for i in range(35)];helperpcs=set()
        for name in helpers:
            window=functions[name];require(len(window)==(3 if name=='capacity' else 13),'Actual helper window length')
            require([x['insn'] for x in window]==[x['insn'] for x in original_functions[name]],'Original helper bytes '+name)
            helperpcs.update(x['pc'] for x in window)
        extra=[x for pc,x in code.items() if pc not in helperpcs and x['insn']&3==3 and
               (x['insn']&127==0x57 or (x['insn']&127 in (7,39) and (x['insn']>>12)&7 in (0,5,6,7)))]
        require(not extra,'No extra vector opcode')
        require(symbols['out']%8==symbols['mask']%8==symbols['e32m4_expected_blocks']%8==0,'Actual alignment')
        require(symbols['__stack_top']-symbols['__bss_end']>=65536,'Actual64KiB stack reserve')
        raw=elf.read_bytes()
        for name in ('dictionary64.bin','indices_u16le.bin','fp_expected640_u32le.bin'):
            require(raw.count((MODEL/name).read_bytes())==1,'Exact unique full payload in ELF '+name)
        own=[x for pc,x in code.items() if pc not in helperpcs and any(
            pc>=f[0]['pc'] and pc<=f[-1]['pc'] for n,f in functions.items() if f and (n.startswith('e32m4_') or n=='arithmetic_main'))]
        require(not [x for x in own if x['insn']&3==3 and (x['insn']&127==0x0f or
                (x['insn']&127==0x73 and (x['insn']>>12)&7))],'No new scalar CSR/fence')
        run([CC.with_name('riscv64-unknown-elf-size'),'-A',elf],root/'size.log')
        backend_proof[backend]=dict(elf=str(elf),sha256=sha(elf),actual_compile=receipt,original_helpers=458,
          extra_RVV=0,new_scalar_CSR_fence=0,stack_gap=symbols['__stack_top']-symbols['__bss_end'])
    for p,h in pins.items():require(sha(p)==h,'Final input drift '+p)
    save(HERE/'compile_result.json',dict(status='HOST_COMPILED_ACTUAL_CFG_AUDIT_PENDING_NO_REFERENCE_NO_DUT',host_runs=len(host),backends=backend_proof,elapsed_seconds=time.monotonic()-begin))
    for p in HERE.rglob('*'):
        if p.is_file() and p.name not in ('execution.log','execution_receipt.json'):pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    print('HOST_COMPILE_COMPLETE_ACTUAL_CFG_PENDING',flush=True)

if __name__=='__main__':main()
