#!/usr/bin/env python3
"""Freeze a compact-output successor, review budget, cross-compile. No VCS."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from contract import (HERE, ROOT, OUT, ANCESTOR, CALIBRATION, ELF_READER, CONST_FIELDS,
                      REV, require, sha, read, save, verify, module, real_fixture,
                      constant_bytes, elf_blob, work)

OWN = ('contract.py','prepare.py','check.py','main.c','validate.h','test_validate.c','test_compact.py','README.md')


def budget(queries, pin=lambda p:None):
    receipt, log = CALIBRATION/'result.json', CALIBRATION/'run.vcs.log'
    for p in (receipt,log): pin(p)
    r = read(receipt)
    require(r['state'] == 'PASS' and r['independent_protocol_checked'], 'Passing calibration required')
    require(r['checked_artifact_hashes'][str(log)] == sha(log), 'Calibration log identity')
    measured = r['measured']['metrics']['trials']
    ref = {t['mode']:t['rdcycle_total'] for t in measured}
    cycles = re.findall(r'FMA_SOC_SUMMARY .*?cycles=([0-9]+)',log.read_text())
    require(len(cycles) == 4 and len(set(cycles)) == 1, 'Calibration cycle counter semantics')
    rate = int(cycles[0])/r['wall_seconds']
    prefixes = list(range(73,73+queries))
    # Engineering envelope, not measurements of this kernel. Two calls/arm;
    # Q64 baseline visits the complete maximum prefix, native visits each prefix.
    baseline = 2*ref['rvv_tiled']*queries*max(prefixes)/137
    native = 2*ref['native_akv']*sum(prefixes)/137
    conservative_cycles = 2*(baseline+native)+2000000
    seconds = conservative_cycles/(rate*.75)
    return dict(state='CLEARED_FOR_BOUNDED_PARENT_RUN' if seconds < 10800 else 'HOLD_EXCEEDS_BUDGET_ENVELOPE',
        estimates_not_measurements=True,calibration_wall_seconds=r['wall_seconds'],
        calibration_simulation_cycles=int(cycles[0]),calibration_cycles_per_wall_second=rate,
        reference_roi_cycles=ref,calibration_image='operator_soc_20261115_all_01',
        target_image='parent activity02-derived current RTL; passive probe overhead not measured',
        projected_two_baseline_calls_cycles=baseline,projected_two_native_calls_cycles=native,
        prefill_vs_decode_schedule_allowance=2.0,non_roi_cycle_allowance=2000000,
        conservative_rate_multiplier=.75,conservative_seconds=seconds,maximum_seconds=10800,
        uncertainty='Different Prefill arithmetic/schedule and system load; not a runtime guarantee. No timeout extension.',
        queries=queries,production_query_threshold=64,query_threshold_covered=queries >= 64,
        whole_model=False,actual_ggml_dispatch=False)


def assembly(inputs, data, c):
    names = dict(query='llama_input_a_start',key='llama_input_b_start',value='llama_input_c_start',
                 mask='llama_input_d_start',golden='llama_golden_start')
    lines = ['.section .rodata.compact,"a",@progbits','.balign 64','.global fixture_begin','fixture_begin:']
    for role,raw in data.items():
        (inputs/(role+'.bin')).write_bytes(raw)
        symbol = names[role]
        lines += ['.balign 64','.global '+symbol,symbol+':','.incbin "'+str(inputs/(role+'.bin'))+'"']
    lines += ['.global fixture_end','fixture_end:','.balign 64','.global llama_case_config','llama_case_config:',
              '.word 0,0,7,0,128,'+str(c['queries'])+',2,256,1,0,0,0',
              '.word 0,0,0x3db504f3,0,0,0,0,0','.zero 100',
              '.section .bss.compact,"aw",@nobits','.balign 64','.global output_before','output_before: .zero 64',
              '.global llama_attention_output_start','llama_attention_output_start:','.zero '+str(c['outputs']*4),
              '.global llama_attention_output_end','llama_attention_output_end:',
              '.global output_after','output_after: .zero 64','.section .note.GNU-stack,"",@progbits']
    (inputs/'data.S').write_text('\n'.join(lines)+'\n')
    header = [f'#define COMPACT_QUERIES {c["queries"]}u',f'#define COMPACT_OUTPUTS {c["outputs"]}u',
              f'#define COMPACT_INPUT_BYTES {c["input_bytes"]}u',
              f'#define COMPACT_INPUT_HASH UINT64_C(0x{c["input_hash"]:016x})',
              '#define COMPACT_CONSTANTS '+','.join(f'UINT64_C(0x{c[k]:x})' for k in CONST_FIELDS)]
    (inputs/'compact_fixture.h').write_text('\n'.join(header)+'\n')
    save(inputs/'fixture.json',c)


def build(output, queries):
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and not output.exists() and
            re.fullmatch(r'operator_prefill_compact_prepare_20261115_[A-Za-z0-9_.-]+',output.name), 'Fresh owned output required')
    original = read(ANCESTOR/'build.json')
    require(original['state'] == 'BUILT_NOT_EXECUTED' and original['sdk_commit'] == REV and
            original['sdk_overlays'] == {} and original['fixture']['first_query'] == 72 and
            original['fixture']['queries'] == 64, 'Wrong frozen ancestor')
    require(sha(ANCESTOR/'source-pins.json') == original['source_pins_sha256'], 'Ancestor pins receipt')
    inherited = read(ANCESTOR/'source-pins.json')
    verify(inherited); verify(original['artifacts'])
    require(sha(original['elf']) == original['elf_sha256'], 'Ancestor ELF identity')
    for name in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','LD_PRELOAD','LD_LIBRARY_PATH',
                 'GCC_EXEC_PREFIX','COMPILER_PATH','CFLAGS','LDFLAGS'):
        require(not os.environ.get(name), 'Compiler injection: '+name)
    output.mkdir(); inputs = output/'inputs'; inputs.mkdir()
    pins, commands = dict(inherited), []
    env = dict(PATH='/usr/bin:/bin',HOME=str(output),LC_ALL='C',TZ='UTC',PYTHONDONTWRITEBYTECODE='1')

    def pin(p):
        p = Path(p).resolve(strict=True); h = sha(p)
        require(str(p) not in pins or pins[str(p)] == h, 'Pin conflict: '+str(p))
        pins[str(p)] = h

    def run(label,argv):
        argv = list(map(str,argv))
        r = subprocess.run(argv,cwd=output,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (output/(label+'.log')).write_bytes(r.stdout)
        commands.append(dict(label=label,argv=argv,returncode=r.returncode))
        # A single receipt is written after commands complete, not rewritten by a worker.
        require(r.returncode == 0, label+': '+r.stdout[-1800:].decode(errors='replace'))
        return r.stdout.decode()

    report = dict(state='FAIL',schema='prefill-compact-v1',rtl_executed=False,target_executed=False,performance_measured=False)
    try:
        for p in (ANCESTOR/'build.json',ANCESTOR/'source-pins.json',ANCESTOR/'commands.json',Path(sys.executable)):
            pin(p)
        for name in OWN:
            pin(HERE/name); shutil.copyfile(HERE/name,inputs/name)
        frozen = inputs/'ancestor'
        shutil.copytree(ANCESTOR/'inputs',frozen)
        data,c = real_fixture(queries,pin)
        assembly(inputs,data,c)
        review = budget(queries,pin)
        save(output/'budget.json',review)
        recipe = [r for r in read(ANCESTOR/'commands.json') if '-c' in r['argv']]
        objects = []
        for i,record in enumerate(recipe):
            argv = [v.replace(str(ANCESTOR/'inputs'),str(frozen)) for v in record['argv']]
            si,oi = argv.index('-c')+1,argv.index('-o')+1
            if argv[si] == str(frozen/'prefill_main.c'): argv[si] = str(inputs/'main.c')
            if argv[si] == str(frozen/'data.S'): argv[si] = str(inputs/'data.S')
            argv.insert(1,'-I'+str(inputs))
            si,oi = argv.index('-c')+1,argv.index('-o')+1
            obj = output/f'{i:02d}.o'; argv[oi] = str(obj)
            cc = Path(argv[0]); pin(cc)
            require('-ffp-contract=off' in argv and '-fno-fast-math' in argv, 'Numerical compiler flags changed')
            dep = output/f'{i:02d}.d'
            deps = [v for j,v in enumerate(argv) if j not in (si-1,oi-1,oi)]+['-M','-MF',str(dep)]
            run(f'deps-{i:02d}',deps)
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                p = Path(name).resolve(strict=True)
                require(not p.is_relative_to(ROOT/'software'), 'Live SDK compiler input')
                pin(p)
            run(f'compile-{i:02d}',argv); objects.append(obj)
        require(len(objects) == len(recipe) == 15, 'Frozen F16 compile recipe changed')
        oldlink = next(r['argv'] for r in read(ANCESTOR/'commands.json') if r['label'] == 'link')
        link = [v.replace(str(ANCESTOR),str(output)).replace(str(output/'inputs'),str(frozen))
                for v in oldlink if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = list(map(str,objects))
        elf = output/'prefill.elf'; link[link.index('-o')+1] = str(elf)
        run('link',link)
        pin(ELF_READER); shutil.copyfile(ELF_READER,inputs/'elf_reader.py')
        reader = module(inputs/'elf_reader.py','compact_prepare_elf')
        raw = elf.read_bytes(); parsed = reader.contract(raw)
        require(elf_blob(raw,parsed,'compact_contract',8*len(CONST_FIELDS)) == constant_bytes(c), 'ELF contract not retained')
        ranges = {name:reader.extent(parsed,name) for name in
                  ('main','compact_full_prefill','compact_validate_all','compact_audit_all','akv_attention_execute_v2_prefill_native')}
        begin,end = ranges['main']
        markers = sorted(pc for pc,word in parsed['words'].items() if begin <= pc < end and word == 0xc0002073)
        reads = sorted(pc for pc,word in parsed['words'].items() if begin <= pc < end and
                       word & 0xfffff07f == 0xc0002073 and word != 0xc0002073)
        require(len(markers) == len(reads) == 2 and markers[0] < reads[0] < reads[1] < markers[1], 'ROI instruction sites/order')
        objdump = cc.with_name(cc.name.replace('gcc','objdump')); pin(objdump)
        dis = run('objdump',[objdump,'-d','-M','no-aliases,numeric',elf])
        require('vfsub.vv' in dis and 'vmflt.vv' in dis and 'vcpop.m' in dis, 'All-output RVV tolerance checker missing')
        for p in inputs.rglob('*'):
            if p.is_file(): pin(p)
        verify(pins)
        save(output/'source-pins.json',pins)
        case = dict(id=f'qwen3_f16_prefill_compact_q72_{71+queries}_kv0',category='prefill_attention',
            elf=str(elf),elf_sha256=sha(elf),source_pins=str(output/'source-pins.json'),timeout_seconds=10800,
            plusargs=['+AKV_PERF','+AKV_SUMMARY'],checker=[str(Path(sys.executable).resolve()),'-B',str(inputs/'check.py'),
                '--build',str(output),'--run','{run}','--log','{log}','--result','{result}'])
        ready = review['state'] == 'CLEARED_FOR_BOUNDED_PARENT_RUN'
        save(output/'cases.json',dict(cases=[case] if ready else []))
        save(output/'held-case.json',dict(case=None if ready else case,dispatch_allowed=ready,budget=review))
        report.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=sha(elf),sdk_commit=REV,sdk_overlays={},
            ancestor=str(ANCESTOR),ancestor_elf_sha256=original['elf_sha256'],fixture=c,elf_ranges=ranges,
            roi_marker_pcs=markers,roi_read_pcs=reads,source_pins_sha256=sha(output/'source-pins.json'),post_pins_match=True,
            budget=review,dispatch_allowed=ready,production_query_threshold_covered=queries >= 64,
            actual_ggml_dispatch=False,runtime_admission=False,
            fflags_contract='No independently derived strict flag gold: FRM=0, VCSR=5, VSTART=0, same-mode repeat equality only',
            unprinted_outputs='All target-checked against captured gold outside ROI; host independently checks first64 and target code/data identity',
            hash_algorithm='FNV1a over little-endian uint64 words, entire input payload / entire output; consistency only')
    except Exception as exc:
        report['error'] = str(exc)
    save(output/'commands.json',commands)
    report['artifacts'] = {str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json',report)
    if report['state'] == 'BUILT_NOT_EXECUTED':
        runpins = dict(pins)
        for p in (output/'source-pins.json',output/'build.json',output/'cases.json',output/'budget.json',elf):
            runpins[str(p)] = sha(p)
        save(output/'run-source-pins.json',runpins)
        cases = read(output/'cases.json')['cases']
        for c in cases: c['source_pins'] = str(output/'run-source-pins.json')
        save(output/'manifest.json',dict(cases=cases))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--queries',type=int,choices=(16,64),default=16)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    r = build(a.output,a.queries)
    print({k:r[k] for k in ('state','error','elf','dispatch_allowed') if k in r})
    raise SystemExit(r['state'] != 'BUILT_NOT_EXECUTED')
