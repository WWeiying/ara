#!/usr/bin/env python3
"""Sole typed16 block-unrolled software candidate; never dispatches a reference."""
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
from model import generate,headers,packed_header,integer_model
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
sp=importlib.util.spec_from_file_location('immutable_compile_helpers',PARENT/'full_e16_mf4_prepare01/prepare.py')
old=importlib.util.module_from_spec(sp);local_model=sys.modules['model'];sys.modules['model']=integer_model
try:sp.loader.exec_module(old)
finally:sys.modules['model']=local_model
sha,save,run=old.sha,old.save,old.run
def emit(path,text):
    with Path(path).open('x') as f:f.write(text)

def main():
    require=old.require
    require(not (HERE/'preflight.json').exists() and not sys.argv[1:],'One exact preparation, no flag sweep/resume')
    source=old.REC/'reconstructed_oracle.c'
    require(sha(source)=='7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91','Original recovered C')
    seeds,rows,blocks,masks=generate()
    bound=dict(SEW=16,LMUL='m8',CAP=512,vtype=11,physical_vector_regs=8,vlenb=128,
        calls=len(rows),results=2096640,guards=8190,helper_instructions=53235,checked_output_bytes=1028,
        span_bytes=1024,physical_a_bytes=2048,physical_b_bytes=2048,physical_out_bytes=2052,
        typed_sentinel=91,sentinel64='005b005b005b005b',tail32='005b005b',fullword_reads_each=128,tail_read_bytes=4,
        dictionary_blocks=len(blocks),max_index=max(max(r['indices']) for r in rows),index_bytes=4095*17*2,
        dictionary_bytes=64*len(blocks),mask_bytes=384,ROM_bytes=64*len(blocks)+4095*17*2+384,
        physical_mask_bytes=128,physical_mask_upper_zero_bytes=64,stack_reserve_bytes=65536,RAM_bytes=1048576,
        seed_rng_final=[s['rng_final'] for s in seeds])
    require(bound['max_index']<65536 and bound['ROM_bytes']+131072+6276<1048576,'Actual index/ROM/pre-link budget')
    require(len(blocks)==3598,'Cross-check actual e16/m8 feasibility block count')
    save(HERE/'preflight.json',bound)
    table,fixture=headers(seeds,rows,blocks,masks)
    emit(HERE/'dictionary.h',table);emit(HERE/'host_fixture.h',fixture);emit(HERE/'packed.h',packed_header())
    save(HERE/'sequence.json',rows);save(HERE/'seed_inputs.json',seeds)
    original=source.read_text();adapted=old.old.runtime_adapt(original);emit(HERE/'original_case.c',adapted)
    packed=adapted.replace('static word a[1024], b[1024], out[1026];',
        'static word a[1024],b[1024];\nstatic word out[1026] __attribute__((aligned(8)));\n#include "dictionary.h"\n#include "packed.h"')
    mask_start=packed.index('                for(unsigned i=0;i<128;++i)mask[i]=0;')
    mask_end=packed.index('                unsigned trials=',mask_start)
    packed=packed[:mask_start]+'                initialize_mask(mask,mode);\n'+packed[mask_end:]
    require(packed.count('for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;')==1,'Exact initialization anchor')
    packed=packed.replace('for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;','initialize_output((uint8_t *)out);')
    start=packed.index('                    unsigned packed=0;');end=packed.index('                    ++checks;',start)
    fallback=packed[start:end]
    packed=packed[:start]+'                    if(packed_mismatch((const uint8_t *)out,checks)){\n'+fallback+'                    }else elements+=cap;\n'+packed[end:]
    packed=packed.replace('if(!cap || cap>1024)','if(cap!=512)')
    require(fallback in packed and packed.count('++checks;')==1 and 'prefix_complete' not in packed,'Original full order/fallback')
    emit(HERE/'case.c',packed)
    emit(HERE/'source.diff',''.join(difflib.unified_diff(adapted.splitlines(True),packed.splitlines(True),fromfile='runtime_original16',tofile='sole_block_unrolled16')))
    archive=HERE/'original';archive.mkdir()
    name='rvv_matrix_e16_m8';linux=old.ARCH/'overlay/opt/ara-tests'/name
    require(sha(linux)=='68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d','Original e16/m8 Linux ELF')
    identity=next(x for x in json.loads((old.REC/'report.json').read_text())['results'] if x['name']==name)
    require(identity['exact_elf_equal'] and identity['disassembly_equal'] and sha(old.REC/name)==sha(linux),'Original reconstruction proof')
    asm=old.ARCH/(name+'.S');header=old.ARCH/'e16/operations.h'
    require(sha(asm)=='a55d6f07a2f69258ffe07378baf08cf72fab2283312b76a8a8b5a5637b35d191','Actual original e16/m8 helper assembly')
    shutil.copyfile(asm,archive/'scenario.S');shutil.copyfile(header,archive/'operations.h')
    inputs=[source,old.REC/'report.json',old.REC/name,linux,old.ARCH/'manifest.json',asm,header,
        PARENT/'m8_block64_feasibility01/REVIEW.md',PARENT/'m8_block64_feasibility01/host_result01.json',
        PARENT/'full_e8_m8_block_unrolled01/prepare.py',PARENT/'full_e8_m8_block_unrolled01/packed.h',
        PARENT/'full_e16_mf4_prepare01/model.py',PARENT/'full_e16_mf4_prepare01/prepare.py',PARENT/'prepare.py']
    runtime=PARENT/'full_e16_mf4_prepare01/runtime';inputs.extend(runtime/n for n in ('startup.S','runtime.c','replay.ld'))
    original_code,_=old.disassemble(linux,archive/'program.dis')
    proof=dict(original_C_bytes_recovered=False,binary_equivalent_reconstruction=True,identity=identity,
        scope=bound,full_order_calls=4095,original_helper_instructions_per_call=13,original_fallback_verbatim=True,
        partitioned=False,reference_started=False,DUT_started=False,backends={},host=[])
    for backend in ('soc','spike'):
        directory=HERE/backend;directory.mkdir();elf=directory/'program.elf'
        emit(directory/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0','-ffunction-sections',
            '-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections',
            '-T',runtime/'replay.ld','-DSEW=16','-I'+str(archive)]
        if backend=='spike':flags.append('-DSPIKE_REFERENCE=1')
        run([old.CC,*flags,HERE/'case.c',archive/'scenario.S',directory/'main.c',runtime/'startup.S',runtime/'runtime.c','-lgcc','-o',elf],directory/'compile.log')
        code,symbols=old.disassemble(elf,directory/'program.dis');save(directory/'symbols.json',symbols)
        helpers={n:old.routine(code,symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(25)]}
        for n,window in helpers.items():old.archived_window(original_code,window);require(len(window)==(3 if n=='capacity' else 13),'Original helper bytes')
        hp={x['pc'] for window in helpers.values() for x in window}
        extra=[pc for pc,i in code.items() if i&3==3 and ((i&127)==0x57 or (i&127) in (7,39) and ((i>>12)&7) in (0,5,6,7)) and pc not in hp]
        require(not extra,'No additional autoRVV')
        require(symbols['__bss_end']<symbols['__stack_top']-65536,'Actual 1MiB and64KiB stack linker bound')
        run([old.CC.with_name('riscv64-unknown-elf-readelf'),'-lW',elf],directory/'segments.log')
        segments=[]
        for line in (directory/'segments.log').read_text().splitlines():
            values=line.split()
            if values and values[0]=='LOAD':
                base,size=int(values[2],16),int(values[5],16);require(0x80000000<=base and base+size<=0x80100000,'Actual load segment inside1MiB')
                segments.append(dict(address=base,mem_bytes=size))
        require(segments,'Actual load segments')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,all_helper_bytes_equal_original=True,
            symbols=symbols,code={str(pc):insn for pc,insn in code.items()},stack_gap=symbols['__stack_top']-symbols['__bss_end'],
            load_segments=segments,extra_vector_instructions=extra)
    for variant in ('original','packed'):
        directory=HERE/('host_'+variant);directory.mkdir()
        shutil.copyfile(HERE/('original_case.c' if variant=='original' else 'case.c'),directory/'case.c');shutil.copyfile(HERE/'host.c',directory/'host.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DSEW=16',
            '-I'+str(archive),'-I'+str(HERE),'-I'+str(directory)]
        if variant=='packed':flags.append('-DPACKED_CASE=1')
        run(['/usr/bin/cc',*flags,directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in range(10):
            log=directory/f'case{mutation}.log';run([directory/'host',str(mutation)],log,expect=-4 if mutation==8 else 0 if mutation==0 else 1)
            if mutation!=8:require('HOST_FULL4095 positions=2096640 guards=8190 masks=524160 calls=4095' in log.read_text(),'Full typed16 Host scope')
            proof['host'].append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log)))
    for mutation in range(10):
        require((HERE/'host_original'/f'case{mutation}.log').read_bytes()==(HERE/'host_packed'/f'case{mutation}.log').read_bytes(),
            'Original vs packed exact full counters/fallback diagnostics')
    save(HERE/'proof.json',proof)
    pins={str(path):sha(path) for path in inputs+[old.CC,old.SPIKE]}
    pins.update({str(path):sha(path) for path in HERE.rglob('*') if path.is_file() and path.suffix!='.pyc'})
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_PENDING_TESLA_REVIEW_NO_REFERENCE_NO_DUT',scope=bound,
        actual_paired_host_runs=20,UBSan_trap=True,full_position_oracle_comparisons=2096640,all1028_byte_flip_negatives=True,
        protected_page_tail4_positive=True,pins_sha256=sha(HERE/'pins.json')))
    print(json.dumps(bound),flush=True)

if __name__=='__main__':main()
