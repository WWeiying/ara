#!/usr/bin/env python3
"""Host and compile only. No reference executor or DUT dispatch."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent
A=SOURCE.parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module
model=load('e32_m1_static_model',SOURCE/'model.py')
load('model',A/'full_e16_mf4_prepare01/model.py')
base=load('sealed_compile_utilities',A/'full_e16_mf4_prepare01/prepare.py')
sha,require=base.sha,base.require
def save(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def emit(path,value):
    with Path(path).open('x') as f:f.write(value)
def run(command,log,expect=0,timeout=90):
    command=list(map(str,command));save(str(log)+'.command.json',dict(command=command,timeout_s=timeout))
    print('COMMAND '+str(log.relative_to(HERE)),flush=True)
    started=time.monotonic();timedout=False;rc=None
    with log.open('x') as f:
        try:rc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
        except subprocess.TimeoutExpired:timedout=True
    receipt=dict(returncode=rc,timed_out=timedout,elapsed_s=time.monotonic()-started,expected_returncode=expect)
    save(str(log)+'.exit.json',receipt)
    require(not timedout and rc==expect,f'{log}: unexpected child outcome {receipt}')
    return receipt

def main():
    require(not sys.argv[1:] and not (HERE/'preflight.json').exists(),'One preparation, no resume/retry')
    model.source_contract()
    sources=[SOURCE/'PLAN.md',SOURCE/'model.py',SOURCE/'packed.h',HERE/'prepare.py',HERE/'host.c',
        *map(Path,model.SOURCE_PINS),A/'full_e16_mf4_prepare01/prepare.py',A/'full_e16_mf4_prepare01/model.py',
        A/'prepare.py',Path(base.old.helper.__file__),Path(base.old.helper.prepare.__file__),base.CC,
        base.CC.with_name('riscv64-unknown-elf-objdump'),base.CC.with_name('riscv64-unknown-elf-nm'),
        Path('/usr/bin/cc').resolve(),A/'recovery22/report.json']
    runtime=A/'full_e16_mf4_prepare01/runtime'
    sources += [runtime/n for n in ('startup.S','runtime.c','replay.ld')]
    initial={str(p):sha(p) for p in sources}
    save(HERE/'preflight.json',dict(status='HOST_COMPILE_ONLY',pins=initial,reference=False,DUT=False))
    print('GENERATE original full5985 exact-table model',flush=True)
    seeds,rows=model.generate()
    save(HERE/'sequence.json',rows);save(HERE/'seed_inputs.json',seeds)
    emit(HERE/'expected.h','#include <stdint.h>\nstatic const uint64_t expected_words[5985][17]={\n'+
        ',\n'.join('{'+','.join(f'UINT64_C(0x{x:016x})' for x in r['words'])+'}' for r in rows)+'\n};\n')
    fixture='struct fixture_row {unsigned seed,op,vl,mode,start;};\nstatic const struct fixture_row fixture_rows[5985]={\n'
    fixture+=',\n'.join('{'+','.join(str(r[k]) for k in ('seed','op','vl','mode','start'))+'}' for r in rows)+'\n};\n'
    for bank in ('a','b'):
        fixture+=f'static const unsigned fixture_{bank}[3][32]={{\n'+',\n'.join('{'+','.join(f'{x}u' for x in s[bank])+'}' for s in seeds)+'\n};\n'
    emit(HERE/'host_fixture.h',fixture)
    original=(A/'recovery22/reconstructed_oracle.c').read_text()
    adapted=base.old.runtime_adapt(original)
    emit(HERE/'original_case.c',adapted)
    packed=adapted.replace('static word a[1024], b[1024], out[1026];',
        'static word a[1024], b[1024];\nstatic word out[1026] __attribute__((aligned(8)));\n#include "expected.h"\n#include "packed.h"')
    packed=packed.replace('for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;','initialize_output(out);')
    start=packed.index('                    unsigned packed=0;');end=packed.index('                    ++checks;',start)
    fallback=packed[start:end]
    packed=packed[:start]+'                    if(packed_mismatch(out,checks)) {\n'+fallback+'                    } else elements+=cap;\n'+packed[end:]
    packed=packed.replace('if(!cap || cap>1024)','if(cap!=32)')
    fpbegin=adapted.index('#if SEW >= 32',adapted.index('word sentinel='))
    fpend=adapted.index('#endif',fpbegin)+len('#endif')
    fpblock=adapted[fpbegin:fpend]
    seedbegin=adapted.index('        uint64_t random=');seedend=adapted.index('        for(unsigned op=',seedbegin)
    seedblock=adapted[seedbegin:seedend]
    def source_guard(text):
        require(text.count(fpblock)==1,'Every original FP assignment/loop must remain')
        require(text.count(seedblock)==1,'Every original seed RNG/init must remain')
        require(fallback in text and 'prefix_complete' not in text and text.count('++checks;')==1,'Full fallback/history')
    source_guard(packed)
    source_negatives=[]
    for name,text in [('delete_fp_a',packed.replace('a[i]=fp_inputs[(i+seed)%8];','')),
                      ('delete_fp_b',packed.replace('b[i]=fp_inputs[(i*3+seed)%8];','')),
                      ('delete_next_seed_rng',packed.replace('random^=random<<13;',''))]:
        try:source_guard(text)
        except (ValueError,AssertionError,RuntimeError) as e:source_negatives.append(dict(name=name,rejected=True,reason=str(e)))
        else:raise ValueError('Source mutation accepted '+name)
    save(HERE/'source_negatives.json',source_negatives)
    emit(HERE/'case.c',packed)
    emit(HERE/'source.diff',''.join(difflib.unified_diff(adapted.splitlines(True),packed.splitlines(True),fromfile='original_runtime',tofile='packed_scalar')))
    # Untyped memcpy interfaces also permit deliberately misaligned Host buffers.
    emit(HERE/'packed.h',(SOURCE/'packed.h').read_text().replace('const uint32_t *p','const void *p').replace('uint32_t *p','void *p'))
    archive=HERE/'original';archive.mkdir()
    for source,name in [(base.ARCH/'rvv_matrix_e32_m1.S','scenario.S'),(base.ARCH/'e32/operations.h','operations.h')]:shutil.copyfile(source,archive/name)
    identity=next(x for x in json.loads((A/'recovery22/report.json').read_text())['results'] if x['name']=='rvv_matrix_e32_m1')
    require(identity['exact_elf_equal'] and identity['disassembly_equal'],'Actual original binary reconstruction')
    host=[]
    for variant in ('original','packed','missing_equal_fp_a','missing_equal_fp_b'):
        directory=HERE/('host_'+variant);directory.mkdir()
        case=adapted if variant=='original' else packed
        for bank,assignment in [('a','a[i]=fp_inputs[(i+seed)%8];'),('b','b[i]=fp_inputs[(i*3+seed)%8];')]:
            wrapped='{'+assignment+f' fp_store({0 if bank=="a" else 1},i,{bank}[i]);'+'}'
            if variant=='missing_equal_fp_'+bank:
                wrapped='if(!(calls==1366 && i==31)) '+wrapped
            require(case.count(assignment)==1,'Unique FP assignment instrumentation')
            case=case.replace(assignment,wrapped)
        emit(directory/'host_case.c',case)
        shutil.copyfile(HERE/'host.c',directory/'host.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
            '-DSEW=32','-I'+str(archive),'-I'+str(HERE)]
        if variant!='original':flags.append('-DPACKED_CASE=1')
        run(['/usr/bin/cc',*flags,directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in (range(12) if variant in ('original','packed') else [0]):
            expected=90 if variant.startswith('missing_') else int(mutation!=0)
            log=directory/f'case{mutation}.log'
            receipt=run([directory/'host',str(mutation)],log,expect=expected)
            if expected==90:
                require('HOST_BLOCK call=1367 every FP call fresh stores, even equal old value' in log.read_text(),'Deleted-store exact first cause')
            else:require('HOST_FULL5985 results=191520 guards=11970 fp_calls=1890 fp_stores=120960' in log.read_text(),'Full Host scope')
            host.append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log),**receipt))
    for n in range(12):require((HERE/'host_original'/f'case{n}.log').read_bytes()==(HERE/'host_packed'/f'case{n}.log').read_bytes(),'Original exact fallback diagnostics/counters')
    originalcode,_=base.disassemble(base.ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m1',archive/'program.dis')
    proof=dict(identity=identity,original_C_bytes_recovered=False,host=host,source_negatives=source_negatives,
        original_fallback_verbatim=True,original_FP_loop_verbatim=True,original_seed_RNG_verbatim=True,
        scope=dict(calls=len(rows),ops=35,results=191520,guards=11970,FP_calls=1890,FP_input_word_stores=120960,
            packed_reads=101745,output_bytes=136,physical_bytes=128,physical_mask_bytes=128,vlm_bytes=4),
        fflags_oracle=False,reference_started=False,DUT_started=False,backends={})
    for backend in ('soc','spike'):
        directory=HERE/backend;directory.mkdir();elf=directory/'program.elf'
        emit(directory/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
            '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
            '-Wl,--build-id=none','-Wl,--gc-sections','-Wl,-Map='+str(directory/'program.map'),
            '-T',runtime/'replay.ld','-DSEW=32','-I'+str(archive)]
        if backend=='spike':flags.append('-DSPIKE_REFERENCE=1')
        run([base.CC,*flags,HERE/'case.c',archive/'scenario.S',directory/'main.c',runtime/'startup.S',runtime/'runtime.c','-lgcc','-o',elf],directory/'compile.log')
        code,symbols=base.disassemble(elf,directory/'program.dis')
        helpers={name:base.routine(code,symbols,name) for name in ['capacity']+[f'op_{i}' for i in range(35)]}
        for name,window in helpers.items():
            base.archived_window(originalcode,window)
            require(len(window)==(3 if name=='capacity' else 13),'Actual original helper instruction count')
        allowed={i['pc'] for window in helpers.values() for i in window}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra,'No additional RVV')
        require(symbols['__bss_end']<symbols['__stack_top']-65536,'Actual64KiB stack reserve')
        save(directory/'symbols.json',symbols)
        run([base.CC.with_name('riscv64-unknown-elf-size'),'-A',elf],directory/'size.log')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,helper_instructions=sum(map(len,helpers.values())),
            extra_vector=extra,stack_gap=symbols['__stack_top']-symbols['__bss_end'],bss_end=symbols['__bss_end'],stack_top=symbols['__stack_top'])
    save(HERE/'proof.json',proof)
    for p,h in initial.items():require(sha(p)==h,'Pre/post input identity '+p)
    pins=dict(initial)
    for p in HERE.rglob('*'):
        if p.is_file() and not p.name.startswith('execution') and p.suffix!='.pyc':pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_COST_REVIEW_PENDING_NO_REFERENCE_NO_DUT',
        host_runs=len(host),source_negative_count=len(source_negatives),proof_sha256=sha(HERE/'proof.json'),pins_sha256=sha(HERE/'pins.json')))
    print('HOST_COMPILED_NO_REFERENCE_NO_DUT',flush=True)
if __name__=='__main__':main()
