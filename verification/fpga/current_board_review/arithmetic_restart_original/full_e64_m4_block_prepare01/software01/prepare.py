#!/usr/bin/env python3
"""One e64/m4 Host/GCC candidate; never execute Spike or a simulator."""
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
A = HERE.parents[1]
MODEL = A / 'full_e64_m4_source_model01'
PROPOSAL = A / 'full_e64_m4_scalar_source_proposal01'
ARCH = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
RUNTIME = A / 'full_e16_mf4_prepare01/runtime'


def require(ok, reason):
    if not ok: raise ValueError(reason)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def save(p, value):
    with Path(p).open('x') as f: json.dump(value, f, indent=2); f.write('\n')


def emit(p, text):
    with Path(p).open('x') as f: f.write(text)


def replace(s, old, new):
    require(s.count(old) == 1, 'Exact one source replacement: ' + old)
    return s.replace(old, new)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module


load('model', A / 'full_e16_mf4_prepare01/model.py')
base = load('immutable_e64m4_compile_utilities', A / 'full_e16_mf4_prepare01/prepare.py')


def run(command, log, expected=0, timeout=90):
    command = list(map(str, command))
    save(str(log)+'.command.json', dict(command=command, timeout_s=timeout, cwd=str(HERE)))
    print('COMMAND ' + str(log.relative_to(HERE)), flush=True)
    start = time.monotonic(); timed = False
    with log.open('x') as f:
        child = subprocess.Popen(command, cwd=HERE, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try: rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed = True; os.killpg(child.pid, signal.SIGKILL); rc = child.wait()
    receipt = dict(returncode=rc, expected_returncode=expected, timed_out=timed,
                   elapsed_s=time.monotonic()-start, pid=child.pid)
    save(str(log)+'.exit.json', receipt)
    require(type(rc) is int and rc == expected and not timed, 'Actual command failure ' + str(log))
    return receipt


def materialize():
    require(not (HERE/'source_entry.json').exists(), 'One materialization only')
    require(sha(PROPOSAL/'CANDIDATE.json') == 'e77b93e4c0d7e73793d506f7a3cd39c0f97337fc30442ceb4cf6d68574f9c124', 'Exact reviewed candidate')
    review = A / 'e64_m4_source_review01/INTEGRATED_PROPOSAL.md'
    require(sha(review) == 'e41152542c2e67ea4f022600b82a46581adf4ef6d77761992d8c441b8c1e40b0', 'Actual integrated source review')
    candidate = read(PROPOSAL/'CANDIDATE.json')
    pins = {**candidate['pins'], **candidate['dependency_pins']}
    pins[str(PROPOSAL/'CANDIDATE.json')] = sha(PROPOSAL/'CANDIDATE.json')
    pins[str(review)] = sha(review)
    for p,h in pins.items(): require(sha(p)==h, 'Frozen source drift '+p)
    original = base.old.runtime_adapt((A/'recovery22/reconstructed_oracle.c').read_text())
    proposed = base.old.runtime_adapt((PROPOSAL/'case_proposal.c').read_text())
    proposed = replace(proposed, '#include "../full_e64_m4_source_model01/fp_period_proposal.h"', '#include "fp_period.h"\n#include "dictionary.h"')
    emit(HERE/'original_case.c', original); emit(HERE/'case.c', proposed)
    emit(HERE/'wrapper.diff', ''.join(difflib.unified_diff((PROPOSAL/'case_proposal.c').read_text().splitlines(True), proposed.splitlines(True))))
    for name, src in [('mask_setup.h', PROPOSAL/'mask_setup.h'), ('packed_output.h', PROPOSAL/'packed_output.h'), ('fp_period.h', MODEL/'fp_period_proposal.h')]:
        shutil.copyfile(src, HERE/name)
    dictionary = (MODEL/'generated01/dictionary64.bin').read_bytes()
    indices = (MODEL/'generated01/indices_u16le.bin').read_bytes()
    require(len(dictionary)==127104 and len(indices)==107730, 'Exact own dictionary dimensions')
    words = struct.unpack('<15888Q', dictionary); ids = struct.unpack('<53865H', indices)
    definition = '#ifndef E64M4_DICTIONARY_H\n#define E64M4_DICTIONARY_H\n#include <stdint.h>\nconst uint64_t e64m4_dictionary[1986][8]={\n'
    definition += ',\n'.join('{'+','.join(f'UINT64_C(0x{x:016x})' for x in words[i:i+8])+'}' for i in range(0,len(words),8))+'\n};\n'
    definition += 'const uint16_t e64m4_block_ids[5985][9]={\n'
    definition += ',\n'.join('{'+','.join(map(str,ids[i:i+9]))+'}' for i in range(0,len(ids),9))+'\n};\n#endif\n'
    emit(HERE/'dictionary.h', definition)
    # Verify the generated numeric initializers independently of their formatter.
    rebuilt = b''.join(struct.pack('<Q',int(x,16)) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',definition))
    raw_ids = definition.split('e64m4_block_ids[5985][9]={',1)[1]
    rebuilt_ids = b''.join(struct.pack('<H',int(x)) for x in re.findall(r'\d+',raw_ids))
    require(rebuilt==dictionary and rebuilt_ids==indices, 'Lossless C dictionary/IDs emission')
    rows = read(MODEL/'generated01/calls.json'); seeds = read(MODEL/'generated01/seed_inputs.json')
    fixture = 'struct fixture_row {unsigned seed,op,vl,mode,start,si;};\nstatic const struct fixture_row fixture_rows[5985]={\n'
    fixture += ',\n'.join('{'+','.join(str(row[k]) for k in ('seed','op','vl','mode','start','trial'))+'}' for row in rows)+'\n};\n'
    for bank in ('a','b'):
        fixture += f'static const uint64_t fixture_{bank}[3][64]={{\n'+',\n'.join('{'+','.join(f'UINT64_C(0x{x:016x})' for x in seed[bank])+'}' for seed in seeds)+'\n};\n'
    emit(HERE/'host_fixture.h', fixture)
    archive = HERE/'original'; archive.mkdir()
    shutil.copyfile(ARCH/'rvv_matrix_e64_m4.S', archive/'scenario.S')
    shutil.copyfile(ARCH/'e64/operations.h', archive/'operations.h')
    for p in [MODEL/'generated01/calls.json',MODEL/'generated01/seed_inputs.json',MODEL/'generated01/gold_u64le.bin',
              MODEL/'generated01/input_pins.json',MODEL/'generated01/result.json',*RUNTIME.glob('*'),
              base.CC,base.CC.with_name('riscv64-unknown-elf-objdump'),base.CC.with_name('riscv64-unknown-elf-nm'),
              base.CC.with_name('riscv64-unknown-elf-size'),Path('/usr/bin/cc').resolve()]:
        if p.is_file(): pins[str(p)] = sha(p)
    for module in list(sys.modules.values()):
        p = getattr(module,'__file__',None)
        if p and str(A.parent) in str(p) and Path(p).is_file(): pins[str(Path(p).resolve())]=sha(p)
    for p in HERE.rglob('*'):
        if p.is_file(): pins[str(p)] = sha(p)
    save(HERE/'source_entry.json',dict(status='SOFTWARE_ONLY_MATERIALIZED_NO_REFERENCE_NO_DUT',pins=pins,
        scope=candidate['scope'],wrapper='immutable arithmetic_restart_original/prepare.py runtime_adapt',
        no_host_rvv_execution=True,reference=False,DUT=False))
    print('MATERIALIZED e64/m4 full5985', flush=True)


def instrument_original(case):
    for bank, expr in [('a','a[i]=fp_inputs[(i+seed)%8];'),('b','b[i]=fp_inputs[(i*3+seed)%8];')]:
        case=replace(case,expr,'{'+expr+f'fp_event({bank}+i,{bank}[i]);'+'}')
    case=replace(case,'for(unsigned i=0;i<128;++i)mask[i]=0;',
                 'for(unsigned i=0;i<128;++i){mask[i]=0;if(i%8==7)mask_event(0,i-7,mask);}')
    case=replace(case,'if(selected(mode,i))mask[i/8]|=1u<<(i%8);',
                 'if(selected(mode,i)){mask[i/8]|=1u<<(i%8);mask_event(1,i,mask);}')
    return replace(case,'for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;',
                   'for(unsigned i=0;i<cap+2;++i){out[i]=sentinel;fresh_event(out+i,out[i]);}')


def host_headers(directory):
    fp=(HERE/'fp_period.h').read_text()
    fp=replace(fp,'    __builtin_memcpy(destination, &value, sizeof(value));',
        '    if (!skip_fp(destination)) {\n    __builtin_memcpy(destination, &value, sizeof(value));\n    fp_event(destination,value);\n    if(duplicate_fp(destination)){__builtin_memcpy(destination,&value,sizeof(value));fp_event(destination,value);}\n    }')
    old='    e64_m4_store(a + (base) + (index), (x)); \\\n    e64_m4_store(b + (base) + (index), (y)); \\'
    new='    if(monitoring && setup_variant==3 && calls==1366 && (base)==0 && (index)==0) { \\\n    e64_m4_store(b + (base) + (index), (y)); \\\n    e64_m4_store(a + (base) + (index), (x)); \\\n    } else { \\\n'+old+'\n    } \\'
    fp=replace(fp,old,new);emit(directory/'fp_period.h',fp)
    mask=(HERE/'mask_setup.h').read_text()
    mask=replace(mask,'    __builtin_memcpy(mask + (offset), &zero, 8); \\',
        '    if(!skip_clear(offset)){__builtin_memcpy(mask + (offset), &zero, 8); mask_event(0,(offset),mask);} \\')
    old='    mask[(index) / 8u] = (uint8_t)(mask[(index) / 8u] | \\\n                                (UINT32_C(1) << ((index) % 8u))); \\'
    mask=replace(mask,old,'    if(!skip_bit(index)){ \\\n'+old+'\n    mask_event(1,(index),mask); } \\')
    mask=replace(mask,'        E64M4_MASK_BIT(0);\n        E64M4_MASK_BIT(1);',
        '        if(monitoring && setup_variant==9 && calls==0){E64M4_MASK_BIT(1);E64M4_MASK_BIT(0);}\n        else{E64M4_MASK_BIT(0);E64M4_MASK_BIT(1);}')
    emit(directory/'mask_setup.h',mask)
    packed=(HERE/'packed_output.h').read_text()
    packed=replace(packed,'    output[(index)] = UINT64_C(0x5b); \\',
        '    if(!skip_fresh(index)){output[(index)] = UINT64_C(0x5b); fresh_event(output+(index),output[(index)]);} \\')
    packed=replace(packed,'    const uint64_t actual = current[(index)]; \\',
        '    const uint64_t actual = current[(index)]; read_event(current+(index),actual); \\')
    packed=replace(packed,'    E64M4_OUTPUT_COMPARE(0);\n    E64M4_OUTPUT_COMPARE(1);\n    return',
        '    E64M4_OUTPUT_COMPARE(0);\n    if(monitoring && setup_variant==13){E64M4_OUTPUT_COMPARE(0);}\n    else {E64M4_OUTPUT_COMPARE(1);}\n    return')
    emit(directory/'packed_output.h',packed)


def software():
    manifest=read(HERE/'source_entry.json');pins=manifest['pins']
    for p,h in pins.items(): require(sha(p)==h,'Preflight drift '+p)
    save(HERE/'software_started.json',dict(status='HOST_GCC_RUNNING_NO_REFERENCE_NO_DUT',pins=pins))
    host=[]
    for variant in ('original','packed'):
        d=HERE/('host_'+variant);d.mkdir();host_headers(d)
        case=(HERE/('original_case.c' if variant=='original' else 'case.c')).read_text()
        if variant=='original': case=instrument_original(case)
        else: case=replace(case,'random^=random<<13;random^=random>>7;random^=random<<17;',
            'if(!(setup_variant==6 && seed==1)){random^=random<<13;random^=random>>7;random^=random<<17;}')
        emit(d/'host_case.c',case);shutil.copyfile(HERE/'host.c',d/'host.c')
        flags=['-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
            '-DSEW=64','-DGOLD_PATH="'+str(MODEL/'generated01/gold_u64le.bin')+'"',
            '-I'+str(HERE/'original'),'-I'+str(HERE)]
        if variant=='packed': flags.append('-DPACKED_CASE=1')
        run(['/usr/bin/cc',*flags,d/'host.c','-o',d/'host'],d/'compile.log')
        for mutation in range(14):
            expected=-signal.SIGILL if mutation==12 else int(mutation!=0)
            log=d/f'case{mutation}.log';receipt=run([d/'host',mutation,0],log,expected)
            if mutation!=12: require('HOST_FULL5985 results=383040 guards=11970 fp_calls=1890 fp_stores=241920' in log.read_text(),'Full Host scope')
            host.append(dict(variant=variant,mutation=mutation,setup_variant=0,log=str(log),sha256=sha(log),**receipt))
        if variant=='packed':
            for setup in range(1,14):
                log=d/f'setup{setup}.log';receipt=run([d/'host',0,setup],log,90)
                require('HOST_BLOCK' in log.read_text(),'Setup/order/fresh negative rejected')
                host.append(dict(variant=variant,mutation=0,setup_variant=setup,log=str(log),sha256=sha(log),**receipt))
    for n in range(14):
        if n!=12: require((HERE/'host_original'/f'case{n}.log').read_bytes()==(HERE/'host_packed'/f'case{n}.log').read_bytes(),'Exact original/packed diagnostic transcript')
    originalcode,_=base.disassemble(ARCH/'overlay/opt/ara-tests/rvv_matrix_e64_m4',HERE/'original/program.dis')
    proof=dict(host=host,scope=manifest['scope'],backends={},fflags_oracle=False,reference=False,DUT=False)
    for backend in ('soc','spike'):
        d=HERE/backend;d.mkdir();elf=d/'program.elf'
        emit(d/'main.c','extern int arithmetic_main(void);\nint main(void){return arithmetic_main();}\n')
        flags=['-O2','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
            '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
            '-Wl,--build-id=none','-Wl,--gc-sections','-Wl,-Map='+str(d/'program.map'),'-T',RUNTIME/'replay.ld',
            '-DSEW=64','-I'+str(HERE/'original')]
        if backend=='spike': flags.append('-DSPIKE_REFERENCE=1')
        run([base.CC,*flags,HERE/'case.c',HERE/'original/scenario.S',d/'main.c',RUNTIME/'startup.S',RUNTIME/'runtime.c','-lgcc','-o',elf],d/'compile.log')
        code,symbols=base.disassemble(elf,d/'program.dis');save(d/'symbols.json',symbols)
        helpers={name:base.routine(code,symbols,name) for name in ['capacity']+[f'op_{i}' for i in range(35)]}
        for name,window in helpers.items():
            base.archived_window(originalcode,window);require(len(window)==(3 if name=='capacity' else 13),'Original exact helper window')
        allowed={x['pc'] for window in helpers.values() for x in window}
        extra=[pc for pc,x in code.items() if x&3==3 and ((x&127)==0x57 or ((x&127) in (7,39) and ((x>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(sum(map(len,helpers.values()))==458 and not extra,'458 helpers/no extraRVV')
        require(symbols['mask']%8==symbols['out']%8==0,'Mask/output alignment')
        require(symbols['__stack_top']-symbols['__bss_end']>=65536,'Actual64KiB stack gap')
        run([base.CC.with_name('riscv64-unknown-elf-size'),'-A',elf],d/'size.log')
        proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,helper_instructions=458,
            extra_vector=extra,stack_gap=symbols['__stack_top']-symbols['__bss_end'])
    save(HERE/'proof.json',proof)
    for p,h in pins.items():require(sha(p)==h,'Postflight drift '+p)
    for p in HERE.rglob('*'):
        if p.is_file() and not p.name.startswith('execution') and p.suffix!='.pyc':pins[str(p)]=sha(p)
    save(HERE/'pins.json',pins)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_PENDING_ACTUAL_CFG_COST_REVIEW',host_runs=len(host),
        proof_sha256=sha(HERE/'proof.json'),pins_sha256=sha(HERE/'pins.json'),reference=False,DUT=False))
    print('HOST_COMPILED_NO_REFERENCE_NO_DUT',flush=True)


if __name__=='__main__':
    require(sys.argv[1:] in (['materialize'],['software']), 'Explicit stage')
    materialize() if sys.argv[1]=='materialize' else software()
