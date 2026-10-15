#!/usr/bin/env python3
"""One reviewed mask-clear candidate: Host and compilation only."""
import argparse
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
OLD=HERE.parent/'software01'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module
prior=load('immutable_software01_prepare',OLD/'prepare.py')
base=prior.base
sha,require=base.sha,base.require
def read(p):return json.loads(Path(p).read_text())
def save(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def emit(p,value):
    with Path(p).open('x') as f:f.write(value)
def run(command,log,expected=0):
    command=list(map(str,command));save(str(log)+'.command.json',dict(command=command,timeout_s=90))
    start=time.monotonic();rc=None;timeout=False
    print('COMMAND '+str(log.relative_to(HERE)),flush=True)
    with log.open('x') as f:
        try:rc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=90).returncode
        except subprocess.TimeoutExpired:timeout=True
    result=dict(returncode=rc,expected_returncode=expected,timed_out=timeout,elapsed_s=time.monotonic()-start)
    save(str(log)+'.exit.json',result)
    require(not timeout and type(rc) is int and rc==expected,'Actual child outcome '+str(log))
    return result
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-review',required=True,type=Path)
    parser.add_argument('--source-review-sha256',required=True);args=parser.parse_args()
    require(sha(args.source_review)==args.source_review_sha256,'Exact independent source review receipt')
    require(not (HERE/'preflight.json').exists(),'One preparation only, no retry/resume')
    pins=read(OLD/'pins.json')
    for p,h in pins.items():require(sha(p)==h,'Old sealed inputs unchanged '+p)
    oldcase=(OLD/'case.c').read_text();candidate=(HERE/'case.c').read_text()
    reverse=candidate.replace('#include "mask_clear.h"\n','').replace('                initialize_mask_zero(mask);',
        '                for(unsigned i=0;i<128;++i)mask[i]=0;')
    require(reverse==oldcase,'ONLY mask-clear replacement/include')
    header=(HERE/'mask_clear.h').read_text()
    require(header.count('__builtin_memcpy(')==16 and header.count('__asm__ __volatile__("" : : : "memory");')==16,'One frozen16-copy lowering')
    for p in (args.source_review,HERE/'case.c',HERE/'mask_clear.h',HERE/'SOURCE_PLAN.md',HERE/'prepare.py',
              OLD/'proof.json',OLD/'software_status.json',OLD/'execution_receipt.json'):
        pins[str(p)]=sha(p)
    save(HERE/'preflight.json',dict(status='SOURCE_REVIEW_BOUND_HOST_COMPILE_ONLY',
        source_review=str(args.source_review),source_review_sha256=args.source_review_sha256,pins=pins,
        reference_authorized=False,DUT_authorized=False))
    for n in ('expected.h','host_fixture.h','packed.h','sequence.json','seed_inputs.json','original_case.c'):
        shutil.copyfile(OLD/n,HERE/n);require(sha(OLD/n)==sha(HERE/n),'Unchanged model/table '+n)
    archive=HERE/'original';archive.mkdir()
    for n in ('scenario.S','operations.h'):shutil.copyfile(OLD/'original'/n,archive/n)
    host=(OLD/'host.c').read_text()
    marker='    unsigned char raw[138];memset(raw,0xa7,sizeof(raw));'
    addition='''    unsigned char dirty[130];memset(dirty,0xa7,sizeof(dirty));
    initialize_mask_zero(dirty+1);
    need(dirty[0]==0xa7 && dirty[129]==0xa7,"mask clear exact128 misaligned guards");
    for(unsigned i=1;i<=128;++i)need(!dirty[i],"all128 dirty mask bytes cleared");
'''
    require(host.count(marker)==1,'Unique footprint test insertion')
    host=host.replace(marker,addition+marker)
    marker='    need(!munmap(p,2*(size_t)page),"unmap");'
    addition='''    memset(p+page-128,0xa7,128);
    initialize_mask_zero(p+page-128);
    for(unsigned i=0;i<128;++i)need(!p[page-128+i],"mask clear128 ends at protected page");
'''
    require(host.count(marker)==1,'Unique page boundary insertion');host=host.replace(marker,addition+marker)
    emit(HERE/'host.c',host)
    host_results=[]
    for variant in ('packed','missing_equal_fp_a','missing_equal_fp_b'):
        directory=HERE/('host_'+variant);directory.mkdir();case=candidate
        for bank,assignment in [('a','a[i]=fp_inputs[(i+seed)%8];'),('b','b[i]=fp_inputs[(i*3+seed)%8];')]:
            wrapped='{'+assignment+f' fp_store({0 if bank=="a" else 1},i,{bank}[i]);'+'}'
            if variant=='missing_equal_fp_'+bank:wrapped='if(!(calls==1366 && i==31)) '+wrapped
            require(case.count(assignment)==1,'Actual original FP assignment');case=case.replace(assignment,wrapped)
        emit(directory/'host_case.c',case);emit(directory/'host.c',host)
        run(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
            '-DSEW=32','-DPACKED_CASE=1','-I'+str(archive),'-I'+str(HERE),directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in (range(12) if variant=='packed' else [0]):
            expected=90 if variant.startswith('missing_') else int(mutation!=0)
            log=directory/f'case{mutation}.log';receipt=run([directory/'host',str(mutation)],log,expected)
            if expected==90:
                require('HOST_BLOCK call=1367 every FP call fresh stores, even equal old value' in log.read_text(),'Deleted store rejection')
            else:
                require(log.read_bytes()==(OLD/'host_original'/f'case{mutation}.log').read_bytes(),'Complete original C/packed transcript equality')
            host_results.append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log),**receipt))
    previous=read(OLD/'proof.json')
    proof=dict(scope=previous['scope'],identity=previous['identity'],new_host_runs=host_results,
        reused_original_host_runs=[r for r in previous['host'] if r['variant']=='original'],
        changed_business_source='ONLY128byte mask clearing; reverse delta byte equality',
        original_FP_loop_verbatim=True,original_RNG_verbatim=True,original_fallback_verbatim=True,
        fflags_oracle=False,reference_started=False,DUT_started=False,backends={})
    runtime=prior.A/'full_e16_mf4_prepare01/runtime'
    # Same flags and runtime as software01, not a second optimization choice.
    for backend in ('soc','spike'):
        directory=HERE/backend;directory.mkdir();elf=directory/'program.elf'
        shutil.copyfile(OLD/backend/'main.c',directory/'main.c')
        command=read(str(OLD/backend/'compile.log')+'.command.json')['command']
        command=[s.replace(str(OLD),str(HERE)) for s in command]
        run(command,directory/'compile.log')
        code,symbols=base.disassemble(elf,directory/'program.dis')
        oldcode,_=base.disassemble(prior.base.ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m1',directory/'original.dis')
        helpers={n:base.routine(code,symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(35)]}
        for n,window in helpers.items():
            base.archived_window(oldcode,window)
            require(len(window)==(3 if n=='capacity' else 13),'Exact original helpers')
        allowed={i['pc'] for w in helpers.values() for i in w}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra,'No extra vector');require(symbols['mask']%8==0,'Actual mask8B alignment')
        require(symbols['__bss_end']<symbols['__stack_top']-65536,'Actual64KiB stack')
        save(directory/'symbols.json',symbols)
        run([base.CC.with_name('riscv64-unknown-elf-size'),'-A',elf],directory/'size.log')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,helper_instructions=sum(map(len,helpers.values())),
            extra_vector=extra,stack_gap=symbols['__stack_top']-symbols['__bss_end'],mask_address=symbols['mask'])
    save(HERE/'proof.json',proof)
    for p,h in pins.items():require(sha(p)==h,'All prior pins unchanged '+p)
    for p in HERE.rglob('*'):
        if p.is_file() and not p.name.startswith('execution') and p.suffix!='.pyc':pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_PENDING_ACTUAL_LOWERING_AND_COST_REVIEW',
        new_host_runs=len(host_results),reused_original_host_runs=12,proof_sha256=sha(HERE/'proof.json'),
        pins_sha256=sha(HERE/'pins.json'),reference=False,DUT=False))
    print('HOST_COMPILED_NO_REFERENCE_NO_DUT',flush=True)
if __name__=='__main__':main()
