"""One reviewed FP-period successor: Host and GCC only, no reference/DUT."""
import difflib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent
A=H.parent
OLD=A/'full_e64_m2_block_software01'
PROPOSAL=A/'full_e64_m2_fp_period_source_proposal01'
s=importlib.util.spec_from_file_location('immutable_software01_utilities',OLD/'prepare.py')
util=importlib.util.module_from_spec(s);s.loader.exec_module(util)
base,model=util.base,util.model
sha,require=util.sha,util.require
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def emit(p,v):
    with Path(p).open('x') as f:f.write(v)
def run(command,log,expected=0):
    # Utility writes its actual wait receipt before enforcing expected outcome.
    old_here=util.HERE;util.HERE=H
    try:return util.run(command,log,expected)
    finally:util.HERE=old_here
def main():
    require(sys.argv[1:] in (['materialize'],['software']),'Explicit single stage')
    if sys.argv[1]=='materialize':materialize()
    else:software()
def materialize():
    require(not (H/'source_entry.json').exists(),'No materialization retry')
    oldpins=json.loads((OLD/'pins.json').read_text())
    for p,h in oldpins.items():require(sha(p)==h,'Sealed01 unchanged '+p)
    review=A/'full_e64_m2_software_review01/FP_PERIOD_SOURCE_REVIEW.md'
    require(sha(review)=='bbc10ce06b9ee3c14ca9fba0322fb6ae22d1cd2f129f4adbfb95735812339264','Actual independent period source review')
    proof=json.loads((PROPOSAL/'STATIC_PROOF.json').read_text())
    for p,h in proof['pins'].items():require(sha(p)==h,'Reviewed proposal pins '+p)
    for n in ('dictionary.h','packed.h','mask_clear.h','host_fixture.h','host_expected.h','original_case.c','sequence.json','seed_inputs.json'):
        shutil.copyfile(OLD/n,H/n);require(sha(OLD/n)==sha(H/n),'Immutable artifact copy '+n)
    shutil.copyfile(PROPOSAL/'fp_period.h',H/'fp_period.h');shutil.copyfile(PROPOSAL/'case_proposal.c',H/'case.c')
    oldblock=(PROPOSAL/'original_FP_block.txt').read_text().rstrip('\n')
    inverse=(H/'case.c').read_text().replace('#include "fp_period.h"\n','').replace('#if SEW >= 32\n                    if(op>=25)refresh_fp_period(a,b,fp_inputs,seed);\n#endif',oldblock)
    require(inverse==(OLD/'case.c').read_text(),'Only periodFP source replacement')
    emit(H/'source.diff',''.join(difflib.unified_diff((OLD/'case.c').read_text().splitlines(True),(H/'case.c').read_text().splitlines(True),fromfile='sealed_software01',tofile='period_software02')))
    archive=H/'original';archive.mkdir()
    for n in ('scenario.S','operations.h'):shutil.copyfile(OLD/'original'/n,archive/n)
    pins=dict(oldpins)
    for p in (review,PROPOSAL/'STATIC_PROOF.json',PROPOSAL/'PLAN.md'):pins[str(p)]=sha(p)
    for p in H.rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    save(H/'source_entry.json',dict(status='EXACT_REVIEWED_FP_PERIOD_SOURCE_HOST_COMPILE_AUTHORIZED_ONLY',pins=pins,calls=5985,FP_calls=1890,FP_stores=120960,reference_authorized=False,DUT_authorized=False))
    print('SOURCE_MATERIALIZED software02',flush=True)
def software():
    require(not (H/'software_started.json').exists(),'Unique Host/compile, no retry')
    entry=json.loads((H/'source_entry.json').read_text());pins=entry['pins']
    for p,h in pins.items():require(sha(p)==h,'Input preflight '+p)
    runtime=A/'full_e16_mf4_prepare01/runtime'
    for p in [base.CC,base.CC.with_name('riscv64-unknown-elf-objdump'),base.CC.with_name('riscv64-unknown-elf-nm'),Path('/usr/bin/cc').resolve(),*(runtime/n for n in ('startup.S','runtime.c','replay.ld'))]:pins[str(p)]=sha(p)
    save(H/'software_started.json',dict(parent_authorization='Unique software02 Host/GCC and complete CFG only',pins=pins,reference=False,DUT=False))
    candidate=(H/'case.c').read_text();original=(H/'original_case.c').read_text();header=(H/'fp_period.h').read_text();results=[];archive=H/'original'
    hook='''
    uintptr_t off=(uintptr_t)p-(uintptr_t)a;
    if(off<256)fp_store(0,(unsigned)(off/8),v);
    else {off=(uintptr_t)p-(uintptr_t)b;fp_store(1,(unsigned)(off/8),v);}
'''
    marker='    __asm__ __volatile__("" : : : "memory");'
    require(header.count(marker)==1,'Unique actual scalar store helper')
    instrumented=header.replace(marker,marker+hook)
    variants=('original','packed','missing_equal_fp_a','missing_equal_fp_b','swap','duplicate','missing_VL0','missing_next_seed','stale_FP_seed','missing_fresh','missing_mask')
    for variant in variants:
        directory=H/('host_'+variant);directory.mkdir();case=original if variant=='original' else candidate;period=instrumented
        if variant=='original':
            for bank,assignment in [('a','a[i]=fp_inputs[(i+seed)%8];'),('b','b[i]=fp_inputs[(i*3+seed)%8];')]:case=case.replace(assignment,'{'+assignment+f' fp_store({0 if bank=="a" else 1},i,{bank}[i]);'+'}')
        if variant.startswith('missing_equal_fp_'):
            bank=variant[-1];period=period.replace('    __builtin_memcpy(p,&v,8);',f'    if(calls==1366 && p=={bank}+31)return;\n    __builtin_memcpy(p,&v,8);')
        if variant=='swap':
            pair='        fp_period_store(dst_a+31,v7);\n        fp_period_store(dst_b+31,v5);'
            require(period.count(pair)==1,'Actual seed0 last pair')
            swapped='        if(calls==1366){fp_period_store(dst_b+31,v5);fp_period_store(dst_a+31,v7);}\n        else {fp_period_store(dst_a+31,v7);fp_period_store(dst_b+31,v5);}'
            period=period.replace(pair,swapped)
        if variant=='duplicate':period=period.replace('        fp_period_store(dst_a+31,v7);','        fp_period_store(dst_a+31,v7);\n        if(calls==1366)fp_period_store(dst_a+31,v7);')
        if variant=='missing_VL0':case=case.replace('if(op>=25)refresh_fp_period','if(op>=25 && vl)refresh_fp_period')
        if variant=='missing_next_seed':case=case.replace('random^=random<<13;random^=random>>7;random^=random<<17;','if(seed!=1){random^=random<<13;random^=random>>7;random^=random<<17;}')
        if variant=='stale_FP_seed':case=case.replace('refresh_fp_period(a,b,fp_inputs,seed);','refresh_fp_period(a,b,fp_inputs,0);')
        if variant=='missing_fresh':case=case.replace('initialize_output(out);','(void)sentinel;')
        if variant=='missing_mask':case=case.replace('initialize_mask_zero(mask);','__builtin_memset(mask,0,4);')
        emit(directory/'host_case.c',case);emit(directory/'fp_period.h',period);shutil.copyfile(H/'host.c',directory/'host.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-DSEW=64','-I'+str(archive),'-I'+str(H)]
        if variant!='original':flags.append('-DPACKED_CASE=1')
        run(['/usr/bin/cc',*flags,directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in (range(13) if variant in ('original','packed') else [0]):
            expected=-4 if mutation==12 else int(mutation!=0) if variant in ('original','packed') else 90
            log=directory/f'case{mutation}.log';r=run([directory/'host',str(mutation)],log,expected)
            if expected==90:require('HOST_BLOCK' in log.read_text(),'Actual source-store/state negative witness')
            elif mutation!=12:require('HOST_FULL5985 results=191520 guards=11970 fp_calls=1890 fp_stores=120960' in log.read_text(),'Full original Host scope')
            results.append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log),**r))
    for mutation in range(12):require((H/'host_original'/f'case{mutation}.log').read_bytes()==(H/'host_packed'/f'case{mutation}.log').read_bytes(),'Complete old/new fulloracle transcript')
    code_original,_=base.disassemble(model.ELF,archive/'program.dis')
    proof=dict(host=results,calls=5985,FP_calls=1890,FP_word_stores=120960,FP_source_sequence_checked=True,scope=json.loads((OLD/'source_entry.json').read_text())['scope'],source_delta='Only reviewed FP-period source replacement',old_HOLD_preserved=True,fflags_oracle=False,reference_started=False,DUT_started=False,backends={})
    for backend in ('soc','spike'):
        directory=H/backend;directory.mkdir();elf=directory/'program.elf'
        emit(directory/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        command=json.loads((OLD/backend/'compile.log.command.json').read_text())['command']
        command=[x.replace(str(OLD),str(H)) for x in command];run(command,directory/'compile.log')
        code,symbols=base.disassemble(elf,directory/'program.dis');save(directory/'symbols.json',symbols)
        helpers={n:base.routine(code,symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(35)]}
        for n,window in helpers.items():base.archived_window(code_original,window);require(len(window)==(3 if n=='capacity' else 13),'Original helper bytes/length')
        allowed={i['pc'] for w in helpers.values() for i in w}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(sum(map(len,helpers.values()))==458 and not extra,'458helper/noextraRVV')
        require(symbols['mask']%8==0 and symbols['__bss_end']<symbols['__stack_top']-65536,'Mask/mapstack')
        require('refresh_fp_period' in symbols,'Actual noninline FP helper')
        _,_,fp=model.tables();location=model.location(elf.read_bytes(),fp,model.load_segments(elf.read_bytes()))
        run([base.CC.with_name('riscv64-unknown-elf-size'),'-A',elf],directory/'size.log')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,helper_instructions=458,extra_RVV=extra,FP640=location,stack_gap=symbols['__stack_top']-symbols['__bss_end'])
    save(H/'proof.json',proof)
    for p,h in pins.items():require(sha(p)==h,'All pre/post pins '+p)
    for p in H.rglob('*'):
        if p.is_file() and not p.name.startswith('execution'):pins[str(p)]=sha(p)
    save(H/'pins.json',pins)
    save(H/'software_status.json',dict(status='HOST_COMPILED_PENDING_ACTUAL_FP_LOWERING_AND_FULL_CFG',Host_runs=len(results),proof_sha256=sha(H/'proof.json'),old_HOLD_preserved=True,reference=False,DUT=False))
    print('HOST_COMPILED_NO_REFERENCE_NO_DUT',flush=True)
if __name__=='__main__':main()
