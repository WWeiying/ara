#!/usr/bin/env python3
"""One typed16 CAP64 flat packed-scalar candidate. No reference dispatch in this program."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
from model import generate, headers, integer_model
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
spec=importlib.util.spec_from_file_location('immutable_full_prepare',PARENT/'full_e16_mf4_prepare01/prepare.py')
old=importlib.util.module_from_spec(spec)
local_model=sys.modules['model'];sys.modules['model']=integer_model
try:spec.loader.exec_module(old)
finally:sys.modules['model']=local_model
sha,save,run=old.sha,old.save,old.run

def emit(path,text):
    if path.exists():
        old.require(path.read_text()==text,'Generated artifact drift '+str(path));return
    with path.open('x') as f:f.write(text)

def main():
    require=old.require
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    require(mode in ('materialize','software'),'Explicit materialize or reviewed software only')
    software=mode=='software'
    require(len(sys.argv)==(4 if software else 2),'Exact mode/review path/hash')
    resume=software
    require((HERE/'preflight.json').exists()==resume,'No source overwrite or software auto retry')
    require(not (HERE/'software_started.json').exists(),'No repeated software execution')
    if software:
        review=Path(sys.argv[2]);report=old.read(review)
        require(sha(review)==sys.argv[3] and report['status']=='NO_BLOCKER_SOURCE_FOR_HOST_AND_COMPILE' and
            report['source_entry_sha256']==sha(HERE/'source_entry.json'),'Actual independent source admission')
        for path,digest in old.read(HERE/'source_entry.json')['pins'].items():require(sha(path)==digest,'Source pin drift '+path)
        save(HERE/'software_started.json',dict(review=str(review),review_sha256=sys.argv[3],one_attempt=True))
    original=old.REC/'reconstructed_oracle.c'
    require(sha(original)=='7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91','Recovered source pin')
    seeds,rows,masks=generate()
    bound=dict(calls=len(rows),sew=16,cap=64,lmul='m1',results=len(rows)*64,
        guards=len(rows)*2,returned_vstart=len(rows),per_call_output_bytes=132,
        flat_expected_bytes=len(rows)*17*8,mask_bytes=384,
        ROM_bytes=len(rows)*17*8+384,reserved_stack_bytes=65536,
        RAM_bytes=1048576,physical_mask_bytes=128,physical_mask_upper_zero_bytes=120,
        actual_vlm_read_bytes=8,observed_register_bytes=128,
        seed_rng_final=[s['rng_final'] for s in seeds])
    require(bound['calls']==4095 and bound['ROM_bytes']+65536+65536<1048576,'Static ROM/stack bound')
    if resume:require(json.loads((HERE/'preflight.json').read_text())==bound,'Preflight unchanged')
    else:save(HERE/'preflight.json',bound)
    table,fixture=headers(seeds,rows,masks)
    emit(HERE/'expected.h',table);emit(HERE/'host_fixture.h',fixture)
    if resume:
        require(json.loads((HERE/'sequence.json').read_text())==rows and
            json.loads((HERE/'seed_inputs.json').read_text())==seeds,'Sequence/input unchanged')
    else:save(HERE/'sequence.json',rows);save(HERE/'seed_inputs.json',seeds)
    source=original.read_text();adapted=old.old.runtime_adapt(source)
    emit(HERE/'original_case.c',adapted)
    packed=adapted.replace('static word a[1024], b[1024], out[1026];',
        'static word a[1024], b[1024];\nstatic word out[1026] __attribute__((aligned(8)));\n#include "expected.h"\n#include "packed.h"')
    mask_start=packed.index('                for(unsigned i=0;i<128;++i)mask[i]=0;')
    mask_end=packed.index('                unsigned trials=',mask_start)
    packed=packed[:mask_start]+'                initialize_mask(mask,mode);\n'+packed[mask_end:]
    require(packed.count('for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;')==1,'Unique initialization')
    packed=packed.replace('for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;', 'initialize_output((uint8_t *)(void *)out);')
    start=packed.index('                    unsigned packed=0;')
    end=packed.index('                    ++checks;',start)
    original_fallback=packed[start:end]
    packed=packed[:start]+'                    if(packed_mismatch((const uint8_t *)(const void *)out,checks)) {\n'+original_fallback+'                    } else elements+=cap;\n'+packed[end:]
    packed=packed.replace('if(!cap || cap>1024)', 'if(cap!=64)')
    require('prefix_complete' not in packed and packed.count('++checks;')==1 and original_fallback in packed,'Original full loops/fallback')
    emit(HERE/'case.c',packed)
    emit(HERE/'source.diff',''.join(difflib.unified_diff(adapted.splitlines(True),packed.splitlines(True),fromfile='runtime_original',tofile='packed_scalar')))
    archive=HERE/'original';archive.mkdir(exist_ok=resume)
    inputs=[original,old.REC/'report.json',old.ARCH/'manifest.json',
        old.ARCH/'overlay/opt/ara-tests/rvv_matrix_e16_m1',old.ARCH/'rvv_matrix_e16_m1.S',old.ARCH/'e16/operations.h',
        PARENT/'full_e16_mf4_prepare01/model.py',PARENT/'full_e16_mf4_prepare01/prepare.py',PARENT/'prepare.py']
    require(sha(inputs[3])=='c9d4a166a1618a221ee99ea0325a83ee34bd2ee4d422574c31a90d182783bc2f','Original ELF')
    recovery=json.loads((old.REC/'report.json').read_text())
    identity=next(x for x in recovery['results'] if x['name']=='rvv_matrix_e16_m1')
    require(identity['exact_elf_equal'] and identity['disassembly_equal'],'Binary-equivalent original C reconstruction')
    require(sha(old.REC/'rvv_matrix_e16_m1')==sha(inputs[3]),'Rebuilt original ELF equality')
    inputs.append(old.REC/'rvv_matrix_e16_m1')
    inputs.extend([Path(old.old.helper.__file__),Path(old.old.helper.prepare.__file__)])
    runtime=PARENT/'full_e16_mf4_prepare01/runtime'
    inputs.extend(runtime/name for name in ('startup.S','runtime.c','replay.ld'))
    inputs.extend([old.CC,old.SPIKE,old.CC.with_name('riscv64-unknown-elf-objdump'),
                   old.CC.with_name('riscv64-unknown-elf-nm'),Path('/usr/bin/cc').resolve()])
    initial_pins={str(p):sha(p) for p in inputs}
    shutil.copyfile(inputs[4],archive/'scenario.S');shutil.copyfile(inputs[5],archive/'operations.h')
    if not software:
        original_code,_=old.disassemble(inputs[3],archive/'program.dis')
        configs=[(pc,insn,(insn>>20)&0x7ff) for pc,insn in original_code.items()
            if insn&127==0x57 and (insn>>12)&7==7 and not insn>>31]
        require(configs and {zimm for _,_,zimm in configs}=={8},'Actual original e16/m1 vtype8')
        source_pins=dict(initial_pins)
        for path in HERE.rglob('*'):
            if path.is_file() and path.suffix!='.pyc':source_pins[str(path)]=sha(path)
        save(HERE/'source_entry.json',dict(status='SOURCE_MATERIALIZED_PENDING_INDEPENDENT_REVIEW',
            pins=source_pins,identity=identity,bounds=bound,original_vtype=8,
            original_config_instruction_count=len(configs),original_C_bytes_recovered=False,
            binary_equivalent_reconstruction=True,Host_runs=0,reference_runs=0,DUT_runs=0))
        print('SOURCE_MATERIALIZED e16/m1 CAP64 vtype8 typed132B full4095',flush=True)
        return
    initial_pins.update(old.read(HERE/'source_entry.json')['pins'])
    initial_pins[str(HERE/'source_entry.json')]=sha(HERE/'source_entry.json')
    initial_pins[str(review)]=sys.argv[3]
    host_results=[]
    print('HOST_START full4095 original and packed, with exact-footprint negatives',flush=True)
    for variant in ('original','packed'):
        directory=HERE/('host_'+variant);directory.mkdir()
        shutil.copyfile(HERE/('original_case.c' if variant=='original' else 'case.c'),directory/'case.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DSEW=16',
            '-I'+str(archive),'-I'+str(HERE),'-I'+str(directory)]
        if variant=='packed':flags.append('-DPACKED_CASE=1')
        # The include is resolved alongside this copy, not the top-level packed case.
        shutil.copyfile(HERE/'host.c',directory/'host.c')
        run(['/usr/bin/cc',*flags,directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in range(10):
            print(f'HOST variant={variant} mutation={mutation}',flush=True)
            log=directory/f'case{mutation}.log'
            run([directory/'host',str(mutation)],log,expect=-4 if mutation==8 else 0 if mutation==0 else 1)
            if mutation!=8:require('HOST_FULL4095 positions=262080 guards=8190 masks=524160 calls=4095' in log.read_text(),'Full Host evidence')
            host_results.append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log)))
    for mutation in [*range(8),9]:
        require((HERE/'host_original'/f'case{mutation}.log').read_bytes()==(HERE/'host_packed'/f'case{mutation}.log').read_bytes(),
            'Original vs packed exact diagnostics/counters differ')
    original_code,_=old.disassemble(inputs[3],archive/'program.dis')
    proof=dict(original_C_bytes_recovered=False,binary_equivalent_reconstruction=True,identity=identity,
        full_order_calls=4095,helper_calls=4095,original_helper_instructions_per_call=13,
        original_fallback_verbatim=True,backends={},host=host_results,reference_started=False,DUT_started=False)
    for backend in ('soc','spike'):
        print('COMPILE '+backend,flush=True)
        directory=HERE/backend;directory.mkdir();elf=directory/'program.elf'
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
            '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
            '-Wl,--build-id=none','-Wl,--gc-sections','-T',runtime/'replay.ld','-DSEW=16','-I'+str(archive)]
        if backend=='spike':flags.append('-DSPIKE_REFERENCE=1')
        main_c=directory/'main.c'
        emit(main_c,'extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        run([old.CC,*flags,HERE/'case.c',archive/'scenario.S',main_c,runtime/'startup.S',runtime/'runtime.c','-lgcc','-o',elf],directory/'compile.log')
        code,symbols=old.disassemble(elf,directory/'program.dis')
        helpers={name:old.routine(code,symbols,name) for name in ['capacity']+[f'op_{i}' for i in range(25)]}
        for name,window in helpers.items():
            old.archived_window(original_code,window)
            require(len(window)==(3 if name=='capacity' else 13),'Original helper length')
        allowed={i['pc'] for window in helpers.values() for i in window}
        extra_vector=[pc for pc,insn in code.items() if insn&3==3 and
            ((insn&127)==0x57 or ((insn&127) in (0x07,0x27) and ((insn>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra_vector,'Compiler added RVV outside original helpers')
        require(symbols['__bss_end']<symbols['__stack_top']-65536,'Actual image stack/link bound')
        save(directory/'symbols.json',symbols)
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,
            bss_end=symbols['__bss_end'],stack_top=symbols['__stack_top'],
            stack_gap=symbols['__stack_top']-symbols['__bss_end'],extra_vector_instructions=extra_vector)
    proof['scalar_adaptation']='Exact132-byte packed initialization/comparison and exact128-byte mask copy; full original fallback'
    proof['bounded_reference']=dict(hard_instructions=4000000,timeout_s=120,max_raw_bytes=768*1024**2,cost_target=3000000,one_attempt=True,DUT_authorized=False)
    save(HERE/'proof.json',proof)
    for path,digest in initial_pins.items():require(sha(path)==digest,'Input changed during preparation '+path)
    pins=initial_pins
    for p in HERE.rglob('*'):
        if p.is_file() and p.suffix not in ('.pyc',):pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_PENDING_INDEPENDENT_REVIEW_NO_REFERENCE_NO_DUT',
        bounds=bound,host_runs=20,host_UBSan_trap=True,reference_instruction_target=3000000,pins_sha256=sha(HERE/'pins.json')))
    print(json.dumps(bound),flush=True)

if __name__=='__main__':main()
