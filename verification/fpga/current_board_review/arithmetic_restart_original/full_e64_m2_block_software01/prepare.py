#!/usr/bin/env python3
"""Single e64/m2 artifact candidate: materialize or Host/GCC only, no reference."""
import difflib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
A=HERE.parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s)
    sys.modules[name]=m;s.loader.exec_module(m);return m
model=load('immutable_e64_m2_static',A/'full_e64_m2_static_feasibility01/static_model.py')
load('model',A/'full_e16_mf4_prepare01/model.py')
base=load('immutable_compile_utilities',A/'full_e16_mf4_prepare01/prepare.py')
sha,require=base.sha,base.require
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def emit(p,s):
    with Path(p).open('x') as f:f.write(s)
def run(command,log,expected=0,timeout=90):
    command=list(map(str,command));save(str(log)+'.command.json',dict(command=command,timeout_s=timeout))
    print('COMMAND '+str(log.relative_to(HERE)),flush=True);start=time.monotonic();timed_out=False
    with log.open('x') as f:
        child=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:timed_out=True;child.kill();rc=child.wait()
    receipt=dict(returncode=rc,expected_returncode=expected,timed_out=timed_out,elapsed_s=time.monotonic()-start,pid=child.pid)
    save(str(log)+'.exit.json',receipt)
    require(not timed_out and type(rc) is int and rc==expected,'Actual child outcome '+str(log))
    return receipt
def packed_header():
    s='#include <stdint.h>\nstatic uint64_t raw_word(const void *p){uint64_t v;__builtin_memcpy(&v,p,8);return v;}\n'
    s+='static void initialize_output(void *p){const uint64_t v=UINT64_C(0x5b);\n'
    s+=''.join(f'__builtin_memcpy((unsigned char *)p+{8*i},&v,8);\n' for i in range(34))+'}\n'
    s+='static unsigned packed_mismatch(const void *p,uint64_t ordinal){const uint16_t *ids=expected_indices[ordinal];\n'
    for block in range(5):
        s+='{const uint64_t *expected=expected_dictionary+8*(unsigned)ids['+str(block)+'];\n'
        for i in range(8 if block<4 else 2):s+=f'if(raw_word((const unsigned char *)p+{block*64+i*8})!=expected[{i}])return 1;\n'
        s+='}\n'
    return s+'return 0;}\n'
def source_guard(candidate,original):
    seedbegin=original.index('        uint64_t random=');seedend=original.index('        for(unsigned op=',seedbegin)
    fpbegin=original.index('#if SEW >= 32',original.index('word sentinel='));fpend=original.index('#endif',fpbegin)+len('#endif')
    fallback=original[original.index('                    unsigned packed=0;'):original.index('                    ++checks;')]
    require(candidate.count(original[seedbegin:seedend])==1,'Original seed/RNG/init verbatim')
    require(candidate.count(original[fpbegin:fpend])==1,'Original every-call FP refresh verbatim')
    require(fallback in candidate and candidate.count('++checks;')==1 and 'prefix_complete' not in candidate,'Full fallback/history')
    require(candidate.count('initialize_output(out);')==1,'Full fresh272B output required')
    require(candidate.count('initialize_mask_zero(mask);')==1,'Full per-group mask clear required')
def materialize():
    require(not (HERE/'source_entry.json').exists(),'No repeated materialization')
    analysis=json.loads((A/'full_e64_m2_static_feasibility01/ANALYSIS.json').read_text())
    review=json.loads((A/'full_e64_m2_static_review01/REVIEW.json').read_text())
    require(review['status']=='NO_BLOCKER_STATIC_SOURCE_MODEL_PLAN_ONLY','Actual static review')
    for p,h in analysis['source_pins'].items():require(sha(p)==h,'Actual static source unchanged '+p)
    kinds,inputs,fp=model.tables();g=model.generate(kinds,inputs,fp)
    require(len(g['rows'])==5985 and len(g['blocks'])==1282,'Actual dict/sequence')
    require(g['full_output_order_sha256']==analysis['model']['full_output_order_sha256'],'Actual static output identity')
    emit(HERE/'packed.h',packed_header())
    table='#include <stdint.h>\nstatic const uint64_t expected_dictionary[]={\n'
    table+=',\n'.join(','.join(f'UINT64_C(0x{(b>>(i*64))&model.MASK64:016x})' for i in range(8)) for b in g['blocks'])+'\n};\n'
    table+='static const uint16_t expected_indices[5985][5]={\n'+',\n'.join('{'+','.join(map(str,r['indices']))+'}' for r in g['rows'])+'\n};\n'
    emit(HERE/'dictionary.h',table)
    words=[[(g['blocks'][r['indices'][i//8]]>>(i%8*64))&model.MASK64 for i in range(34)] for r in g['rows']]
    emit(HERE/'host_expected.h','#include <stdint.h>\nstatic const uint64_t expected_words[5985][34]={\n'+',\n'.join('{'+','.join(f'UINT64_C(0x{v:016x})' for v in r)+'}' for r in words)+'\n};\n')
    fixture='struct fixture_row {unsigned seed,op,vl,mode,start;};\nstatic const struct fixture_row fixture_rows[5985]={\n'
    fixture+=',\n'.join('{'+','.join(str(r[k]) for k in ('seed','op','vl','mode','start'))+'}' for r in g['rows'])+'\n};\n'
    seeds=[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed;a=[];b=[]
        for i in range(32):
            rng^=(rng<<13)&model.MASK64;rng^=rng>>7;rng^=(rng<<17)&model.MASK64
            x,y=rng,rng>>19
            if i%8==0:x=y=0
            elif i%8==1:x,y=model.MASK64,1
            elif i%8==2:x,y=1<<63,model.MASK64
            elif i%8==3:y=64
            a.append(x);b.append(y)
        seeds.append(dict(seed=seed,a=a,b=b,rng_final=rng))
    for bank in ('a','b'):fixture+=f'static const uint64_t fixture_{bank}[3][32]={{\n'+',\n'.join('{'+','.join(f'UINT64_C(0x{x:016x})' for x in s[bank])+'}' for s in seeds)+'\n};\n'
    emit(HERE/'host_fixture.h',fixture);save(HERE/'sequence.json',g['rows']);save(HERE/'seed_inputs.json',seeds)
    adapted=base.old.runtime_adapt((model.REC/'reconstructed_oracle.c').read_text());emit(HERE/'original_case.c',adapted)
    candidate=adapted.replace('static word a[1024], b[1024], out[1026];','static word a[1024], b[1024];\nstatic word out[1026] __attribute__((aligned(8)));\n#include "dictionary.h"\n#include "packed.h"\n#include "mask_clear.h"')
    candidate=candidate.replace('for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;','initialize_output(out);')
    start=candidate.index('                    unsigned packed=0;');end=candidate.index('                    ++checks;',start);fallback=candidate[start:end]
    candidate=candidate[:start]+'                    if(packed_mismatch(out,checks)) {\n'+fallback+'                    } else elements+=cap;\n'+candidate[end:]
    candidate=candidate.replace('if(!cap || cap>1024)','if(cap!=32)').replace('for(unsigned i=0;i<128;++i)mask[i]=0;','initialize_mask_zero(mask);')
    source_guard(candidate,adapted);emit(HERE/'case.c',candidate)
    emit(HERE/'source.diff',''.join(difflib.unified_diff(adapted.splitlines(True),candidate.splitlines(True),fromfile='runtime_original',tofile='packed_scalar')))
    negative=[]
    for name,mutated in [('delete_FP_a',candidate.replace('a[i]=fp_inputs[(i+seed)%8];','')),('delete_FP_b',candidate.replace('b[i]=fp_inputs[(i*3+seed)%8];','')),('delete_next_seed_RNG',candidate.replace('random^=random<<13;','')),('delete_fresh_output',candidate.replace('initialize_output(out);','')),('delete_mask_clear',candidate.replace('initialize_mask_zero(mask);',''))]:
        try:source_guard(mutated,adapted)
        except ValueError as ex:negative.append(dict(name=name,rejected=True,reason=str(ex)))
        else:raise ValueError('Accepted source deletion '+name)
    save(HERE/'source_negatives.json',negative)
    archive=HERE/'original';archive.mkdir()
    shutil.copyfile(model.ASM,archive/'scenario.S');shutil.copyfile(model.HEADER,archive/'operations.h')
    pins=dict(analysis['source_pins']);pins[str(A/'full_e64_m2_static_review01/REVIEW.json')]=sha(A/'full_e64_m2_static_review01/REVIEW.json')
    for p in HERE.rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    save(HERE/'source_entry.json',dict(status='SOURCE_MATERIALIZED_HOST_COMPILE_AUTHORIZED_NO_REFERENCE',pins=pins,scope=analysis['scope'],ROM_bytes=147466,reference_authorized=False,DUT_authorized=False))
    print('SOURCE_MATERIALIZED e64/m2 full5985',flush=True)
def software():
    require(not (HERE/'software_started.json').exists(),'One software execution only')
    source=json.loads((HERE/'source_entry.json').read_text());pins=dict(source['pins'])
    for p,h in pins.items():require(sha(p)==h,'Source preflight '+p)
    runtime=A/'full_e16_mf4_prepare01/runtime'
    for p in [base.CC,base.CC.with_name('riscv64-unknown-elf-objdump'),base.CC.with_name('riscv64-unknown-elf-nm'),Path('/usr/bin/cc').resolve(),*(runtime/n for n in ('startup.S','runtime.c','replay.ld'))]:pins[str(p)]=sha(p)
    save(HERE/'software_started.json',dict(parent_scope='Software/Host/GCC/CFG only, not Spike or VCS',pins=pins))
    adapted=(HERE/'original_case.c').read_text();candidate=(HERE/'case.c').read_text();source_guard(candidate,adapted)
    results=[];archive=HERE/'original'
    for variant in ('original','packed','missing_equal_fp_a','missing_equal_fp_b','missing_fresh','missing_seed','missing_mask'):
        directory=HERE/('host_'+variant);directory.mkdir();case=adapted if variant=='original' else candidate
        if variant=='missing_fresh':case=case.replace('initialize_output(out);','(void)sentinel;')
        if variant=='missing_seed':case=case.replace('random^=random<<13;random^=random>>7;random^=random<<17;','if(seed!=1){random^=random<<13;random^=random>>7;random^=random<<17;}')
        if variant=='missing_mask':case=case.replace('initialize_mask_zero(mask);','__builtin_memset(mask,0,4);')
        for bank,assignment in [('a','a[i]=fp_inputs[(i+seed)%8];'),('b','b[i]=fp_inputs[(i*3+seed)%8];')]:
            wrapped='{'+assignment+f' fp_store({0 if bank=="a" else 1},i,{bank}[i]);'+'}'
            if variant=='missing_equal_fp_'+bank:wrapped='if(!(calls==1366 && i==31)) '+wrapped
            require(case.count(assignment)==1,'Exact FP instrumentation');case=case.replace(assignment,wrapped)
        emit(directory/'host_case.c',case);shutil.copyfile(HERE/'host.c',directory/'host.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DSEW=64','-I'+str(archive),'-I'+str(HERE)]
        if variant!='original':flags.append('-DPACKED_CASE=1')
        run(['/usr/bin/cc',*flags,directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in (range(13) if variant in ('original','packed') else [0]):
            expect=90 if variant.startswith('missing_') else -4 if mutation==12 else int(mutation!=0)
            log=directory/f'case{mutation}.log';r=run([directory/'host',str(mutation)],log,expect)
            if variant.startswith('missing_equal'):require('HOST_BLOCK call=1367 every FP call fresh stores, even equal old value' in log.read_text(),'Missing equal FP write witness')
            elif variant.startswith('missing_'):require('HOST_BLOCK' in log.read_text(),'Actual deleted state rejected')
            elif mutation!=12:require('HOST_FULL5985 results=191520 guards=11970 fp_calls=1890 fp_stores=120960' in log.read_text(),'Full Host scope')
            results.append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log),**r))
    for mutation in range(12):require((HERE/'host_original'/f'case{mutation}.log').read_bytes()==(HERE/'host_packed'/f'case{mutation}.log').read_bytes(),'Exact original/packed transcript')
    original_code,_=base.disassemble(model.ELF,archive/'program.dis')
    proof=dict(host=results,full_calls=5985,FP_calls=1890,original_FP_loop_verbatim=True,original_RNG_verbatim=True,original_fallback_verbatim=True,fflags_oracle=False,reference_started=False,DUT_started=False,backends={})
    for backend in ('soc','spike'):
        directory=HERE/backend;directory.mkdir();elf=directory/'program.elf'
        emit(directory/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-Wl,-Map='+str(directory/'program.map'),'-T',runtime/'replay.ld','-DSEW=64','-I'+str(archive)]
        if backend=='spike':flags.append('-DSPIKE_REFERENCE=1')
        run([base.CC,*flags,HERE/'case.c',archive/'scenario.S',directory/'main.c',runtime/'startup.S',runtime/'runtime.c','-lgcc','-o',elf],directory/'compile.log')
        code,symbols=base.disassemble(elf,directory/'program.dis');save(directory/'symbols.json',symbols)
        helpers={n:base.routine(code,symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(35)]}
        for n,window in helpers.items():base.archived_window(original_code,window);require(len(window)==(3 if n=='capacity' else 13),'Exact helper length')
        require(sum(map(len,helpers.values()))==458,'458 actual helper instructions')
        allowed={x['pc'] for w in helpers.values() for x in w}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra,'No extra RVV');require(symbols['mask']%8==0,'Actual mask alignment')
        require(symbols['__bss_end']<symbols['__stack_top']-65536,'Actual stack/map gap')
        run([base.CC.with_name('riscv64-unknown-elf-size'),'-A',elf],directory/'size.log')
        raw=elf.read_bytes();_,_,fp=model.tables();location=model.location(raw,fp,model.load_segments(raw))
        dictionary=b''.join(int(x,16).to_bytes(8,'little') for x in __import__('re').findall(r'UINT64_C\(0x([0-9a-f]+)\)',(HERE/'dictionary.h').read_text()))
        require(raw.count(dictionary)==1,'Complete actual dictionary uniquely linked')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,helper_instructions=458,extra_vector=extra,stack_gap=symbols['__stack_top']-symbols['__bss_end'],FP640=location,dictionary_bytes=len(dictionary))
    save(HERE/'proof.json',proof)
    for p,h in pins.items():require(sha(p)==h,'All pre/post pins '+p)
    for p in HERE.rglob('*'):
        if p.is_file() and not p.name.startswith('execution'):pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_CFG_COST_REVIEW_PENDING_NO_REFERENCE_NO_DUT',host_runs=len(results),proof_sha256=sha(HERE/'proof.json'),reference=False,DUT=False))
    print('HOST_COMPILED_NO_REFERENCE_NO_DUT',flush=True)
if __name__=='__main__':
    require(sys.argv[1:] in (['materialize'],['software']),'Explicit materialize/software mode')
    materialize() if sys.argv[1]=='materialize' else software()
