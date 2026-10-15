#!/usr/bin/env python3
"""One full482 scalar64 strategy: Host equivalence, SoC ELF, one Spike; never DUT."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'prepared02'
CASE=OLD/'prepared/macc_disjoint_e8_m4_prefix482'
ID='macc_disjoint_e8_m4_prefix482_scalar64'
OLD_ID='macc_disjoint_e8_m4_prefix482'
ROOT=HERE.parents[5]
CC=ROOT/'install/riscv-gcc/bin/riscv64-unknown-elf-gcc'
OBJDUMP=CC.with_name('riscv64-unknown-elf-objdump')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA='rv64gcv_zvl1024b'
import model


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def run(command,log,expected=0,timeout=30):
    started=time.monotonic()
    try:
        with log.open('x') as stream:
            actual=subprocess.run(list(map(str,command)),stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        receipt=dict(command=list(map(str,command)),actual_returncode=actual.returncode,
                     elapsed_s=time.monotonic()-started,timeout_s=timeout,retries=0)
    except subprocess.TimeoutExpired:
        save(log.with_suffix('.execution.json'),dict(command=list(map(str,command)),actual_returncode=None,
             timed_out=True,timeout_s=timeout,retries=0))
        raise
    save(log.with_suffix('.execution.json'),receipt)
    require(type(actual.returncode) is int and actual.returncode==expected,'Actual exit '+str(log))
    return receipt


def replace(text,before,after):
    require(text.count(before)==1,'Source anchor drift: '+before)
    return text.replace(before,after)


def initialize():
    require(not (HERE/'prepared').exists(),'Fresh preparation only; no overwrite/retry')
    old_status=read(OLD/'status.json')
    identity=read(HERE.parent/'identity02/report.json')
    require(old_status['status']=='READY_ORIGINAL_MACC_PREFIX482_HOST_SPIKE_NOT_DUT' and
            identity['whole_elf_byte_equal'] is True and identity['original_sha256']==
            '608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d','Actual original identity')
    require(sha(HERE.parent/'identity02/reconstructed_oracle.c')==identity['reconstructed_c_sha256'],
            'Binary-equivalent original source binding')
    pins={str(p):sha(p) for p in [HERE.parent/'identity02/report.json',
         HERE.parent/'identity02/reconstructed_oracle.c',HERE.parent/'identity02/rvv_integer_macc_accumulators_restart_e8_m4',
         OLD/'status.json',OLD/'expected_inputs.json',OLD/'historical_identity.json',OLD/'reference/status.json',
         HERE.parent/'terminal_resume20261011.md',CC,OBJDUMP,SPIKE,*HERE.glob('*.py'),*HERE.glob('*.c'),*HERE.glob('*.inc')]}
    for p in CASE.rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    for name in ('startup.S','runtime.c','replay.ld'):
        p=OLD/'prepared'/name;pins[str(p)]=sha(p)
    save(HERE/'input_pins02.json',pins)
    gold=model.generate()
    old_expected=read(OLD/'expected_inputs.json')
    require(len(gold['rows'])==len(old_expected),'Complete original scope length')
    for actual,want in zip(gold['rows'],old_expected):
        require({k:actual[k] for k in want}==want,'Full original tuple/input/output digest mismatch')
    require(len(gold['rows'])==482 and gold['rows'][-1]['trial']==481 and
            (gold['rows'][-1]['vl'],gold['rows'][-1]['vstart'])==(512,256),'Last original boundary')
    prepared=HERE/'prepared';prepared.mkdir();original=prepared/'original';original.mkdir()
    for p in (CASE/'original').iterdir():
        if p.is_file():shutil.copyfile(p,original/p.name)
    for name in ('startup.S','runtime.c','replay.ld'):
        shutil.copyfile(OLD/'prepared'/name,prepared/name)
    source=(CASE/'case.c').read_text()
    optimized=replace(source,'static word a[1024], b[1024], out[1026];',
        'static word a[1024] __attribute__((aligned(8))), b[1024] __attribute__((aligned(8))), out[1026] __attribute__((aligned(8)));')
    optimized=replace(optimized,'static uint8_t mask[128];','static uint8_t mask[128] __attribute__((aligned(8)));\n#include "tables.h"')
    optimized=replace(optimized,'    unsigned cap=capacity();','    unsigned cap=capacity();\n    if(cap!=512){text("MACC_OPT_SCOPE_FAIL_CAP\\n");return 90;}')
    before='''                for(unsigned i=0;i<128;++i)mask[i]=0;
                for(unsigned i=0;i<cap;++i)
                    if(selected(mode,i))mask[i/8]|=1u<<(i%8);'''
    optimized=replace(optimized,before,'''                /* Each call below writes its complete physical predicate. */''')
    before='''                    for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;
                    for(unsigned i=0;i<cap;++i)
                        out[i+1]=initial_destination(accumulator,i);'''
    optimized=replace(optimized,before,'''                    if(checks>=482 || seed || op || rm ||
                       prefix_shapes[checks].vl!=vl || prefix_shapes[checks].start!=start ||
                       prefix_shapes[checks].accumulator!=accumulator || prefix_shapes[checks].mode!=mode) {
                        text("MACC_OPT_SCOPE_FAIL_TUPLE\\n");return 91;
                    }
                    for(unsigned i=0;i<64;++i) {
                        ((volatile packed64 *)a)[i]=prefix_inputs[0][i];
                        ((volatile packed64 *)b)[i]=prefix_inputs[1][i];
                    }
                    for(unsigned i=0;i<16;++i)
                        ((volatile packed64 *)mask)[i]=prefix_masks[mode][i];
                    for(unsigned i=0;i<64;++i)
                        ((volatile packed64 *)out)[i]=prefix_initial[accumulator][i];
                    out[512]=prefix_initial[accumulator][64]&255;
                    out[513]=sentinel;''')
    begin=optimized.index('                    unsigned packed=0;')
    end=optimized.index('                    ++checks;',begin)
    optimized=optimized[:begin]+(HERE/'oracle64.inc').read_text()+optimized[end:]
    for name in ('initial_destination','scalar_value'):
        optimized=replace(optimized,'static word '+name+'(','static word __attribute__((unused)) '+name+'(')
    optimized=replace(optimized,'static unsigned selected(','static unsigned __attribute__((unused)) selected(')
    optimized=replace(optimized,'static const unsigned kinds[]','static const unsigned kinds[] __attribute__((unused))')
    # The RNG and complete outer enumeration remain exact original source text.
    begin=source.index('    for(unsigned seed=');end=source.index('        for(unsigned op=',begin)
    require(source[begin:end]==optimized[begin:optimized.index('        for(unsigned op=',begin)],'Global RNG changed')
    anchor='        for(unsigned op=0;op<OPERATION_COUNT;++op)'
    optimized=replace(optimized,anchor,'''        /* Keep original RNG stores live before the redundant per-call fresh copies. */
        for(unsigned i=0;i<64;++i)
            if(((volatile packed64 *)a)[i]!=prefix_inputs[0][i] ||
               ((volatile packed64 *)b)[i]!=prefix_inputs[1][i]) {
                text("MACC_OPT_RNG_FAIL\\n");return 92;
            }
'''+anchor)
    require(source.count('if(checks==482) goto prefix_complete;')==optimized.count('if(checks==482) goto prefix_complete;')==1,
            'Original full prefix bounding changed')
    (prepared/'case.c').write_text(optimized)
    (prepared/'original_prefix.c').write_text(source)
    (prepared/'tables.h').write_text(model.c_tables(gold))
    (prepared/'optimization.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True),optimized.splitlines(True))))
    (prepared/'main.c').write_text((CASE/'main.c').read_text().replace(OLD_ID,ID))
    save(HERE/'model.json',gold)
    save(HERE/'static_scope.json',dict(calls=482,predecessors=481,results=246784,guards=964,
        low_returned_vstart_checks=482,high_status_checks=482,helper_instructions=6266,
        physical_mask_bytes=128,capacity=512,vlenb=128,original_global_RNG_unchanged=True,
        output_array_elements=1026,result_address_relative_to_out=1,
        scalar_init_words=64,scalar_init_final_bytes=2,scalar_oracle_load_words=65,
        ignored_last_read_high_bytes=6,all_original_patterns=5,
        per_call_fresh_initialized_bytes=512+512+128+514,
        redundant_a_b_and_per_call_mask_writes_explicit=True,
        scalar_tables_bytes=2*64*8+4*16*8+5*65*8+482*65*8+482*6,
        whole_original_linux_source_byte_equivalence_inherited=True,optimized_ELF_byte_equivalence_claim=False,
        full22400_accepted=False,Linux_execution=False,DUT_runs=0))
    return gold,pins


def host(gold):
    folder=HERE/'host';folder.mkdir();prepared=HERE/'prepared'
    positive=[];captures={}
    for label,name in (('original','original_prefix.c'),('optimized','case.c')):
        source=(prepared/name).read_text()
        source=replace(source,'__asm__ volatile("csrr %0,vlenb":"=r"(max_start));','max_start=128;')
        source+='\nunsigned host_accumulator(void){return accumulator_trial;}\n'
        path=folder/(label+'.c');path.write_text(source)
        run(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-DSEW=8','-I'+str(prepared),
             '-I'+str(prepared/'original'),path,HERE/'host_adapter.c','-o',folder/label],folder/(label+'.compile.log'))
        capture=folder/(label+'.bin');log=folder/(label+'.log')
        receipt=run([folder/label,capture,'0'],log)
        captures[label]=capture
        require('HOST_END calls=482 injected=0 result=0' in log.read_text(),'Host positive full count')
        positive.append(dict(label=label,execution=receipt,capture_sha256=sha(capture)))
    require(captures['original'].read_bytes()==captures['optimized'].read_bytes(),'Original vs optimized full byte capture mismatch')
    data=captures['optimized'].read_bytes();offset=0
    for row in gold['rows']:
        wanted=struct.pack('<7Q',row['trial'],0,row['vl'],512,row['vstart'],0,row['accumulator'])
        wanted+=bytes(gold['a']+gold['b']+gold['masks'][row['mode']]+[91]+row['old']+[91]+[91]+row['output']+[91])
        require(data[offset:offset+len(wanted)]==wanted,'Independent byte oracle call'+str(row['trial']))
        offset+=len(wanted)
    require(offset==len(data)==482*(56+512+512+128+514+514),'Missing capture bytes')
    mutations=['active','prestart','maskedoff','tail','left_guard','right_guard','vstart_low','return_high',
               'dropped_accumulator','last_result_byte','unused_after_guard_permission']
    negatives=[]
    for number,name in enumerate(mutations,1):
        expected=0 if number==11 else 1
        logs=[];receipts=[]
        for label in ('original','optimized'):
            log=folder/(label+'.'+name+'.log');capture=folder/(label+'.'+name+'.bin')
            receipts.append(run([folder/label,capture,str(number)],log,expected=expected))
            text=log.read_text();require('HOST_END calls=482 injected=1 result='+str(expected) in text,'Mutation not reached')
            require(('RVV_MATRIX_FAIL op=' in text)==(expected==1),'Mutation rejection changed')
            logs.append(text)
        require(logs[0]==logs[1],'Original vs optimized failure semantics differ: '+name)
        negatives.append(dict(name=name,actual_result=expected,executions=receipts))
    save(folder/'status.json',dict(status='PASS_HOST_FULL482_BYTE_EQUIVALENT_AND_MUTATIONS_NOT_DUT',
        positives=positive,all_calls=482,complete_byte_capture_size=len(data),
        original_vs_optimized_byte_identical=True,independent_byte_oracle=True,mutations=negatives,
        expected_failures=10,original_extra_bytes_permission_preserved=True))


def instructions(dis,name):
    body=dis.split('<'+name+'>:\n')[1].split('\n\n')[0]
    return [dict(pc=int(m[1],16),insn=m[2],text=m[3]) for m in
            re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$',body,re.M)]


def build():
    prepared=HERE/'prepared';entries={}
    flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld','-DSEW=8',
           '-I'+str(prepared),'-I'+str(prepared/'original'),'-fstack-usage']
    original_dis=(OLD/'soc/program.dis').read_text()
    for backend in ('soc','spike'):
        folder=HERE/backend;folder.mkdir();elf=folder/(ID+'.elf')
        command=[CC,*flags]+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
        receipt=run(command+[prepared/'case.c',prepared/'original/scenario.S',prepared/'main.c',
                    prepared/'startup.S',prepared/'runtime.c','-lgcc','-o',elf],folder/'compile.log')
        run([OBJDUMP,'-d',elf],folder/'program.dis')
        dis=(folder/'program.dis').read_text()
        routine=instructions(dis,'op_0')
        old=instructions(original_dis,'op_0')
        require(len(routine)==len(old)==13 and [r['insn'] for r in routine]==[r['insn'] for r in old] and
                routine[8]['insn']=='b5042c57','Original13 helper bytes changed')
        nm=subprocess.check_output([CC.with_name('riscv64-unknown-elf-nm'),'-n','-S',elf],text=True,timeout=15)
        symbols={}
        for line in nm.splitlines():
            tokens=line.split()
            if len(tokens)==3:symbols[tokens[2]]=dict(address=int(tokens[0],16),size=0)
            elif len(tokens)==4:symbols[tokens[3]]=dict(address=int(tokens[0],16),size=int(tokens[1],16))
        for name,length in (('a',1024),('b',1024),('out',1026),('mask',128)):
            require(symbols[name]['address']%8==0 and symbols[name]['size']==length,'Physical storage/alignment '+name)
        vector_pcs={r['pc'] for name in ['capacity']+['op_'+str(i) for i in range(8)]
                    for r in instructions(dis,name) if r['text'].startswith('v')}
        all_vectors={int(m[1],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(v\S+)',dis,re.M)}
        require(all_vectors==vector_pcs,'New vector instruction outside original assembly')
        bss_end=symbols['__bss_end']['address'];stack=symbols['__stack_top']['address']
        require(0x80000000<=bss_end<stack-65536 and stack<0x80100000<=0x80200000,'L2/2MiB/stack collision')
        stack_files=list(folder.glob('*.su'))
        require(stack_files,'Missing actual stack-usage report')
        frames=[]
        for path in stack_files:
            for line in path.read_text().splitlines():
                fields=line.split('\t')
                require(len(fields)==3 and fields[2]=='static','Dynamic/unbounded stack frame')
                frames.append(dict(function=fields[0],bytes=int(fields[1])))
        require(sum(f['bytes'] for f in frames)<65536,'Conservative sum of all C frames exceeds reserved stack')
        entry=dict(path=str(elf),sha256=sha(elf),runtime_id=ID,source_label='rvv_integer_macc_accumulators_restart_e8_m4',
                   configurations=482,pass_markers=[f'MACC_PREFIX_PASS {ID} trials=482',f'BOARD_CASE_PASS {ID}',
                   'BOARD_REPLAY_PASS','RVV_MATRIX_PASS sew=8 vlmax=512 cases=482 elements=246784 errors=0 seeds=5 guard_tail_mask_vstart=checked'],
                   original13_routine=routine,actual_compile=receipt,new_vector_instructions=0,
                   symbols=symbols,memory=dict(mapped_Spike_bytes=2*1024*1024,linker_bytes=1024*1024,
                   bss_end=bss_end,stack_top=stack,reserved_stack_bytes=65536,
                   conservative_sum_all_C_frames=sum(f['bytes'] for f in frames),frames=frames))
        save(folder/'program.json',entry);entries[backend]=entry
    return entries


def main():
    try:
        gold,pins=initialize()
        host(gold)
        print('FULL482 STATIC+HOST FULLBYTE+MUTATIONS PASS',flush=True)
        entries=build()
        print('SOC+SPIKE ELF ORIGINAL13 NO_NEW_VECTOR MEMORY PASS',flush=True)
        save(HERE/'PRE_REFERENCE.json',dict(status='HOST_AND_ELFS_READY_NO_REFERENCE_YET',programs=entries,
             model_sha256=sha(HERE/'model.json'),pins={**pins,**{str(p):sha(p) for p in HERE.rglob('*') if p.is_file()}}))
    except BaseException as error:
        save(HERE/'STOPPED02.json',dict(status='PREPARATION_FAILED_NO_RETRY',error=repr(error),DUT_runs=0))
        raise


if __name__=='__main__':
    main()
