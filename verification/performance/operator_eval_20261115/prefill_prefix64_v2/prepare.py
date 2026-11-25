#!/usr/bin/env python3
"""Prepare captured queries0..63 batch64 via frozen ancestor recipes; no VCS."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from contract import (HERE, ROOT, OUT, ANCESTOR, PREDECESSOR, CALIBRATION, ELF_READER, CONST_FIELDS,
                      REV, require, sha, read, save, verify, module, real_fixture,
                      constant_bytes, elf_blob, work)

OWN = ('contract.py','prepare.py','check.py','main.c','validate.h','test_validate.c','test_prefix64.py','README.md')


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
    require(queries == 64, 'Only batch64 queries0..63 budget')
    prefixes = list(range(1,queries+1))
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
        first_query=0,queries=queries,production_query_threshold=64,
        query_count_threshold_satisfied=True,production_dispatch_verified=False,forced_sdk_api=True,
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
            re.fullmatch(r'operator_prefill_prefix64_prepare_20261115_[A-Za-z0-9_.-]+',output.name), 'Fresh owned output required')
    original = read(ANCESTOR/'build.json')
    require(original['state'] == 'BUILT_NOT_EXECUTED' and original['sdk_commit'] == REV and
            original['sdk_overlays'] == {} and original['fixture']['first_query'] == 72 and
            original['fixture']['queries'] == 64, 'Wrong frozen ancestor')
    require(sha(ANCESTOR/'source-pins.json') == original['source_pins_sha256'], 'Ancestor pins receipt')
    inherited = read(ANCESTOR/'source-pins.json')
    verify(inherited); verify(original['artifacts'])
    predecessor = read(PREDECESSOR/'build.json')
    require(predecessor['schema'] == 'prefill-compact-v1' and
            predecessor['fixture']['first'] == 72 and predecessor['fixture']['queries'] == 64 and
            sha(PREDECESSOR/'source-pins.json') == predecessor['source_pins_sha256'], 'Frozen compact predecessor identity')
    predecessor_pins = read(PREDECESSOR/'run-source-pins.json')
    verify(predecessor_pins)
    for path,digest in predecessor_pins.items():
        require(path not in inherited or inherited[path] == digest, 'Ancestor pin conflict: '+path)
        inherited[path] = digest
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

    report = dict(state='FAIL',schema='prefill-prefix64-v2',rtl_executed=False,target_executed=False,performance_measured=False)
    try:
        for p in (ANCESTOR/'build.json',ANCESTOR/'source-pins.json',ANCESTOR/'commands.json',PREDECESSOR/'build.json',PREDECESSOR/'run-source-pins.json',Path(sys.executable)):
            pin(p)
        for name in OWN:
            pin(HERE/name); shutil.copyfile(HERE/name,inputs/name)
        frozen = inputs/'ancestor'
        shutil.copytree(ANCESTOR/'inputs',frozen)
        data,c = real_fixture(queries,pin)
        assembly(inputs,data,c)
        review = budget(queries,pin)
        save(output/'budget.json',review)
        expected = work(c)
        save(output/'workload.json',dict(first_query=0,last_query=63,queries=64,
            kv_capacity=256,visible_prefixes=list(range(1,65)),visible_prefix_sum=2080,
            outputs_per_trial=16384,calls=4,order=[0,1,1,0],native_calls=2,
            native_commands_per_call=len(expected),panel4_commands_per_call=2048,
            paired_pv_loads_per_call=2080,full_commands_per_call=1,refill_commands_per_call=0,
            release_commands_per_call=1,native_qk_scalar_fmas_per_call=532480,
            native_pv_scalar_fmas_per_call=532480,local_replay_bytes_per_native_call=1064960,
            external_payload_bytes_per_native_call=33344,baseline_qk_scalar_fmas_per_call=1048576,
            baseline_pv_scalar_fmas_including_padded_rows=1081344,
            forced_sdk_api=True,batch64_shape=True,production_dispatch_verified=False))
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
        case = dict(id='qwen3_f16_prefill_prefix64_q0_63_kv0',category='prefill_attention',
            elf=str(elf),elf_sha256=sha(elf),source_pins=str(output/'source-pins.json'),timeout_seconds=10800,
            plusargs=['+AKV_PERF','+AKV_SUMMARY'],checker=[str(Path(sys.executable).resolve()),'-B',str(inputs/'check.py'),
                '--build',str(output),'--run','{run}','--log','{log}','--result','{result}'])
        ready = review['state'] == 'CLEARED_FOR_BOUNDED_PARENT_RUN'
        save(output/'cases.json',dict(cases=[case] if ready else []))
        save(output/'held-case.json',dict(case=None if ready else case,dispatch_allowed=ready,budget=review))
        report.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=sha(elf),sdk_commit=REV,sdk_overlays={},
            ancestor=str(ANCESTOR),ancestor_elf_sha256=original['elf_sha256'],
            compact_predecessor=str(PREDECESSOR),compact_predecessor_elf_sha256=predecessor['elf_sha256'],
            fixture=c,elf_ranges=ranges,
            roi_marker_pcs=markers,roi_read_pcs=reads,source_pins_sha256=sha(output/'source-pins.json'),post_pins_match=True,
            budget=review,dispatch_allowed=ready,query_count_threshold_satisfied=True,
            batch64_sdk_evaluation=True,production_dispatch_verified=False,forced_sdk_api=True,
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
        for p in (output/'source-pins.json',output/'build.json',output/'cases.json',output/'budget.json',output/'workload.json',elf):
            runpins[str(p)] = sha(p)
        save(output/'run-source-pins.json',runpins)
        cases = read(output/'cases.json')['cases']
        for c in cases: c['source_pins'] = str(output/'run-source-pins.json')
        save(output/'manifest.json',dict(cases=cases))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--queries',type=int,choices=(64,),default=64)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    r = build(a.output,a.queries)
    print({k:r[k] for k in ('state','error','elf','dispatch_allowed') if k in r})
    raise SystemExit(r['state'] != 'BUILT_NOT_EXECUTED')
