#!/usr/bin/env python3
"""Single reviewed Host/compile execution; never invokes Spike or a simulator."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import generate as g
HERE,A,OLD=g.HERE,g.A,g.OLD
require,sha,save,emit,load=g.require,g.sha,g.save,g.emit,g.load

def run(command, log, expected=0):
    command=list(map(str,command));save(str(log)+'.command.json',dict(command=command,timeout_s=90))
    start=time.monotonic();rc=None;timeout=False
    print('COMMAND '+str(log.relative_to(HERE)),flush=True)
    with log.open('x') as stream:
        try:rc=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=90).returncode
        except subprocess.TimeoutExpired:timeout=True
    receipt=dict(returncode=rc,expected_returncode=expected,timed_out=timeout,elapsed_s=time.monotonic()-start)
    save(str(log)+'.exit.json',receipt)
    require(not timeout and type(rc) is int and rc==expected,'Actual child outcome '+str(log))
    return receipt

def instrument_original(text):
    for bank in ('a','b'):
        expression='a[i]=fp_inputs[(i+seed)%8];' if bank=='a' else 'b[i]=fp_inputs[(i*3+seed)%8];'
        text=g.replace(text,expression,'{'+expression+f'fp_store({int(bank=="b")},i,{bank}[i]);'+'}')
    text=g.replace(text,'for(unsigned i=0;i<128;++i)mask[i]=0;',
        'for(unsigned i=0;i<128;++i){mask[i]=0;if(i%8==7)mask_event(0,i-7,mask);}')
    text=g.replace(text,'if(selected(mode,i))mask[i/8]|=1u<<(i%8);',
        'if(selected(mode,i)){mask[i/8]|=1u<<(i%8);mask_event(1,i,mask);}')
    return text

def instrument_header(text, variant):
    for bank, expression in [('a','a[(I)]=q[(I)%8u];'),('b','b[(I)]=q[(3u*(I))%8u];')]:
        wrapped='{'+expression+f'fp_store({int(bank=="b")},(I),{bank}[(I)]);'+'}'
        if variant=='missing_equal_fp_'+bank:
            wrapped='if(!(calls==1366 && (I)==63u))'+wrapped
        text=g.replace(text,expression,wrapped)
    if variant=='FP_pair_order':
        text=g.replace(text,'    E32M2_FP_PAIR(0u);\n    E32M2_FP_PAIR(1u);',
            '    E32M2_FP_PAIR(1u);\n    E32M2_FP_PAIR(0u);')
    for i in range(0,128,8):
        statement=f'__builtin_memcpy(mask+{i},&zero,8);'
        text=g.replace(text,statement,statement+f' mask_event(0,{i},mask);')
    text=g.replace(text,'mask[(I)/8u]=(uint8_t)(mask[(I)/8u] | (UINT32_C(1)<<((I)%8u)));',
        'mask[(I)/8u]=(uint8_t)(mask[(I)/8u] | (UINT32_C(1)<<((I)%8u))); mask_event(1,(I),mask);')
    if variant=='missing_equal_mask_clear':
        text=g.replace(text,'__builtin_memcpy(mask+120,&zero,8); mask_event(0,120,mask);',
            'if(calls!=0){__builtin_memcpy(mask+120,&zero,8); mask_event(0,120,mask);}')
    if variant=='missing_mask_bit':
        text=g.replace(text,'    E32M2_MASK_BIT(63u);','    if(calls!=0) E32M2_MASK_BIT(63u);',count=2)
    if variant=='mask_bit_order':
        text=g.replace(text,'        E32M2_MASK_BIT(0u);\n        E32M2_MASK_BIT(1u);',
            '        E32M2_MASK_BIT(1u);\n        E32M2_MASK_BIT(0u);')
    return text

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-review',type=Path,required=True)
    parser.add_argument('--source-review-sha256',required=True);args=parser.parse_args()
    require(sha(args.source_review)==args.source_review_sha256,'Exact integrated source review')
    manifest=json.loads((HERE/'SOURCE_FREEZE.json').read_text());pins=manifest['pins']
    for p,h in pins.items():require(sha(p)==h,'Source pin drift '+p)
    pins[str(args.source_review)]=sha(args.source_review)
    prior=load('m1_immutable_prepare',OLD/'prepare.py');base=prior.base
    runtime=A/'full_e16_mf4_prepare01/runtime'
    for p in [Path(base.CC),base.CC.with_name('riscv64-unknown-elf-objdump'),base.CC.with_name('riscv64-unknown-elf-nm'),
              Path('/usr/bin/cc').resolve(),*[runtime/n for n in ('startup.S','runtime.c','replay.ld')],
              Path(base.__file__),Path(base.old.__file__),Path(base.old.helper.__file__),
              Path(base.old.helper.prepare.__file__),A/'recovery22/report.json']:
        pins[str(p)]=sha(p)
    save(HERE/'preflight.json',dict(status='INTEGRATED_SOURCE_REVIEW_BOUND_HOST_COMPILE_ONLY',pins=pins,
        source_review=str(args.source_review),source_review_sha256=args.source_review_sha256))
    host=[]
    variants=('original','packed','missing_equal_fp_a','missing_equal_fp_b','FP_pair_order',
              'missing_equal_mask_clear','missing_mask_bit','mask_bit_order')
    for variant in variants:
        directory=HERE/('host_'+variant);directory.mkdir()
        case=(HERE/('original_case.c' if variant=='original' else 'case.c')).read_text()
        if variant=='original':case=instrument_original(case)
        else:emit(directory/'scalar_setup.h',instrument_header((HERE/'scalar_setup.h').read_text(),variant))
        emit(directory/'host_case.c',case);shutil.copyfile(HERE/'host.c',directory/'host.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
               '-DSEW=32','-I'+str(HERE/'original'),'-I'+str(HERE)]
        if variant!='original':flags.append('-DPACKED_CASE=1')
        run(['/usr/bin/cc',*flags,directory/'host.c','-o',directory/'host'],directory/'compile.log')
        for mutation in (range(12) if variant in ('original','packed') else [0]):
            expected=int(mutation!=0) if variant in ('original','packed') else 90
            log=directory/f'case{mutation}.log';receipt=run([directory/'host',str(mutation)],log,expected)
            if expected==90:require('HOST_BLOCK' in log.read_text(),'Fresh order mutation rejected')
            else:require('HOST_FULL5985 results=383040 guards=11970 fp_calls=1890 fp_stores=241920' in log.read_text(),'Full Host scope')
            host.append(dict(variant=variant,mutation=mutation,log=str(log),sha256=sha(log),**receipt))
    for n in range(12):require((HERE/'host_original'/f'case{n}.log').read_bytes()==(HERE/'host_packed'/f'case{n}.log').read_bytes(),'Full original fallback exact transcript')
    identity=next(x for x in json.loads((A/'recovery22/report.json').read_text())['results'] if x['name']=='rvv_matrix_e32_m2')
    require(identity['exact_elf_equal'] and identity['disassembly_equal'],'Original reconstructed C binary identity')
    originalcode,_=base.disassemble(base.ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m2',HERE/'original/program.dis')
    proof=dict(scope=manifest['scope'],identity=identity,host=host,backends={},fflags_oracle=False,reference=False,DUT=False)
    for backend in ('soc','spike'):
        directory=HERE/backend;directory.mkdir();elf=directory/'program.elf'
        emit(directory/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
               '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
               '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
               '-Wl,--build-id=none','-Wl,--gc-sections','-Wl,-Map='+str(directory/'program.map'),
               '-T',str(runtime/'replay.ld'),'-DSEW=32','-I'+str(HERE/'original')]
        if backend=='spike':flags.append('-DSPIKE_REFERENCE=1')
        run([base.CC,*flags,HERE/'case.c',HERE/'original/scenario.S',directory/'main.c',runtime/'startup.S',runtime/'runtime.c','-lgcc','-o',elf],directory/'compile.log')
        code,symbols=base.disassemble(elf,directory/'program.dis')
        helpers={n:base.routine(code,symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(35)]}
        for n,window in helpers.items():
            base.archived_window(originalcode,window);require(len(window)==(3 if n=='capacity' else 13),'Original helper length')
        allowed={i['pc'] for w in helpers.values() for i in w}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra,'No extra RVV');require(symbols['mask']%8==symbols['out']%8==0,'Mask/output aligned')
        require(symbols['__stack_top']-symbols['__bss_end']>=65536,'Actual64KiB stack')
        save(directory/'symbols.json',symbols)
        run([base.CC.with_name('riscv64-unknown-elf-size'),'-A',elf],directory/'size.log')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,helper_instructions=sum(map(len,helpers.values())),
            extra_vector=extra,stack_gap=symbols['__stack_top']-symbols['__bss_end'])
    save(HERE/'proof.json',proof)
    for p,h in pins.items():require(sha(p)==h,'Pre/post pins '+p)
    for p in HERE.rglob('*'):
        if p.is_file() and not p.name.startswith('execution') and p.suffix!='.pyc':pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_PENDING_ACTUAL_CFG_COST_REVIEW',
        host_runs=len(host),proof_sha256=sha(HERE/'proof.json'),pins_sha256=sha(HERE/'pins.json'),reference=False,DUT=False))
    print('HOST_COMPILED_NO_REFERENCE_NO_DUT',flush=True)

if __name__=='__main__':main()
