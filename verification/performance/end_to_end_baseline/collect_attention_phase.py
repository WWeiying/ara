#!/usr/bin/env python3
"""Independent host-only raw replay of the frozen quantized Attention phase observation."""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
VERIFY=Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
RUNS=VERIFY/'verification/out'
WORKER=RUNS/'e2e_output_phase_vcs_20261106_01'
WORKER_SHA='dd3d3e96ec31d0321902d1c16656f2a6bade5486b629dafe713dbe02af754f2d'
WORKER_PINS_SHA='1ce214bd811e2dfb9b4e548130ef1c0e2ab6beb92be0cdaa775d2db0576025ef'
BUILD=RUNS/'e2e_output_phase_build_20261106_02'
BUILD_SHA='e8683a23c40f956d0276a1f125d35f2414795462d13a27ad8a7492cb2bee7446'
ELF_SHA='557ac6aa65f219260b4da09fd591cef6c453f57e56d6fbb165597b32b7582011'
OUT=RUNS/'e2e_attention_phase_collect_20261106_01'
EXCLUSIVE=('init','quantize','qk','coefficients','pv','finish')


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def admit_worker(worker):
    require(worker.get('state')=='REAL_ATTENTION_PHASE_OBSERVATION_RTL_PASS' and worker.get('child_pid') is None and
            all(worker.get(k) is True for k in ('phase_observation_measured','independent_protocol_checked',
                                               'quantitative_phase_fractions_allowed','post_pins_match')) and
            all(worker.get(k) is False for k in ('whole_model','optimization_speedup_claim','synthesis_run','exact_elf_spike_executed')),
            'Exact terminal observation worker acceptance required')
    require(worker.get('source_pins_sha256')==WORKER_PINS_SHA and worker.get('elf_sha256')==ELF_SHA and
            worker.get('build_result_sha256')==BUILD_SHA and worker.get('elf')==str(BUILD/'output_phase.elf'),
            'Wrong accepted worker/build/ELF identity')


def admit_build(program):
    expected=dict(state='OUTPUT_PHASE_ELF_BUILT_NOT_EXECUTED',elf_sha256=ELF_SHA,
        baseline='output_tile_original_object',candidate='output_tile_observation_only_clone',
        heads=6,dim=128,visible=128,trials=4,order=[0,1,1,0],commands_per_trial=8,outputs_per_trial=768,
        reused_objects=16,rebuilt_objects=2,internal_timestamps_per_probed_call=46,
        quantitative_phase_interpretation_requires_measured_overhead_at_most=.05,simulation_count=0)
    require(all(program.get(k)==v for k,v in expected.items()) and program.get('binding_nested_in_qk') is True and
            all(program.get(k) is False for k in ('whole_model','target_executed','performance_measured','production_changes')),
            'Wrong original/probe build or nested binding scope')


def quantitative_summary(measured):
    rows=measured['trials']
    require(len(rows)==4 and [r['trial'] for r in rows]==list(range(4)) and
            [r['probed'] for r in rows]==[0,1,1,0],'Exact ABBA rows required')
    require(all(type(r['cycles']) is int and r['cycles']>0 for r in rows),'Positive integer whole-call cycles required')
    # Exact integer inequality: reject either direction and exactly five percent.
    for observed,baseline in ((rows[1],rows[0]),(rows[2],rows[3])):
        require(abs(observed['cycles']-baseline['cycles'])*20<baseline['cycles'],
                'Per-pair absolute perturbation must be strictly below five percent')
    original=rows[0]['cycles']+rows[3]['cycles'];probed=rows[1]['cycles']+rows[2]['cycles']
    require(abs(probed-original)*20<original,'Aggregate perturbation must be strictly below five percent')
    totals={phase:0 for phase in EXCLUSIVE};nested=0;unobserved=0
    for row in (rows[1],rows[2]):
        phases=row['phases'];exclusive=sum(phases[p+'_cycles'] for p in EXCLUSIVE)
        require(exclusive==row['exclusive_phase_cycles'] and 0<=exclusive<=row['cycles'] and
                row['unobserved_cycles']==row['cycles']-exclusive and
                0<phases['binding_cycles']<=phases['qk_cycles'],'Exclusive/nested accounting differs')
        for phase in EXCLUSIVE:totals[phase]+=phases[phase+'_cycles']
        nested+=phases['binding_cycles'];unobserved+=row['unobserved_cycles']
    require(sum(totals.values())+unobserved==probed,'Exclusive phases plus unobserved must conserve complete-call cycles')
    return dict(uninstrumented_mean_cycles=original/2,probed_mean_cycles=probed/2,
        aggregate_perturbation=probed/original-1,
        paired_perturbations=[rows[1]['cycles']/rows[0]['cycles']-1,rows[2]['cycles']/rows[3]['cycles']-1],
        absolute_each_pair_and_aggregate_below_five_percent=True,
        exclusive_phases={p:dict(mean_cycles=value/2,fraction_of_probed_call=value/probed) for p,value in totals.items()},
        unobserved=dict(mean_cycles=unobserved/2,fraction_of_probed_call=unobserved/probed),
        binding_nested_in_qk=dict(mean_cycles=nested/2,fraction_of_probed_call=nested/probed,add_to_exclusive=False),
        other_than_coefficients_pv_qk_fraction=(probed-totals['coefficients']-totals['pv']-totals['qk'])/probed,
        denominator='Mean of complete observed calls, not uninstrumented time or just instrumented regions')


def numerical_replay(text,golden,worker):
    import check_output_phase as checker
    measured=checker.check(text,golden)
    require(measured==worker['measured'],'Raw numerical/CSR/phase replay differs field-by-field')
    require(measured['quantitative_phase_fractions_allowed'] is True and measured['paired_bitexact'] is True and
            measured['csr_bitexact'] is True and measured['whole_model'] is False and
            measured['optimization_speedup_claim'] is False,'Observation acceptance/claim scope differs')
    summary=quantitative_summary(measured)
    require(summary['uninstrumented_mean_cycles']==measured['uninstrumented_cycles'] and
            summary['probed_mean_cycles']==measured['probed_cycles'] and
            summary['paired_perturbations']==measured['paired_perturbations'] and
            summary['aggregate_perturbation']==measured['measured_perturbation'],'Independent ABBA arithmetic differs')
    return measured,summary


def protocol_agreement(replayed,recorded,worker):
    require(replayed==recorded and replayed.get('status')=='PASS' and replayed.get('issues')==[],
            'Raw protocol replay must agree in every field, not merely status')
    require(replayed.get('elf_sha256')==ELF_SHA and replayed.get('sim_image_sha256')==worker['image_pins'],
            'Protocol program/design identity differs')


def source_replay():
    import build_output_phase as build
    sources={rel:(ROOT/rel).read_text() for rel in build.SOURCE_SHAS}
    for rel,expected in build.SOURCE_SHAS.items():require(digest(ROOT/rel)==expected,'Original source identity differs')
    generated,operations=build.transform_sources(sources)
    require(len(operations)==10,'Expected exact ten observation insertions')
    for rel,text in generated.items():
        require((BUILD/'inputs/probe'/rel).read_text()==text,'Observation clone differs: '+rel)
    expected=dict(scope='observation-only exact-anchor clone; no math or approximation changes',
        original_sha256=build.SOURCE_SHAS,operations=operations,
        generated_sha256={rel:digest(BUILD/'inputs/probe'/rel) for rel in build.SOURCE_SHAS})
    require(read(BUILD/'transform.json')==expected,'Registered transform report differs')
    require((BUILD/'inputs/main'/HERE.relative_to(ROOT)/'output_phase_main.c').read_bytes()==(HERE/'output_phase_main.c').read_bytes(),
            'Actual completed-state caller source differs')
    inventory=read(BUILD/'source-pins.json');copies={}
    for name in inventory:
        path=Path(name)
        if path.suffix not in ('.c','.h','.cpp','.S','.ld'):continue
        for root,label in ((ROOT,'main'),(VERIFY,'verify')):
            if path.is_relative_to(root):
                target=BUILD/'inputs'/label/path.relative_to(root)
                if target.is_file():copies[str(path)]=target
                break
    remap=lambda v:build.remap_input(v,copies,BUILD)
    records={r['label']:r['argv'] for r in read(BUILD/'commands.json')}
    native={r['label']:r['argv'] for r in read(build.NATIVE/'commands.json')}
    jobs=[('caller',native['compile-1'],BUILD/'inputs/main'/HERE.relative_to(ROOT)/'output_phase_main.c',[]),
          ('probe',native['compile-17'],BUILD/'inputs/probe'/build.Q/'output_tile/runtime.c',[
           '-Dquant_output_tile_execute=output_phase_execute','-Dquant_output_tile_workspace_bytes=output_phase_workspace_bytes',
           '-Dquant_output_tile_inner_execute=output_phase_inner_execute','-Dquant_output_tile_unused_grouped_execute=output_phase_unused_grouped_execute'])]
    for label,recipe,source,defines in jobs:
        expected=[remap(v) for v in recipe]
        if label=='probe':expected=[v.replace('-I'+str(BUILD/'inputs/main'),'-I'+str(BUILD/'inputs/probe'),1)
                                   if v.startswith('-I'+str(BUILD/'inputs/main')) else v for v in expected]
        expected[expected.index('-c')+1]=str(source);expected[expected.index('-o')+1]=str(BUILD/(label+'.o'))
        expected[1:1]=defines
        require(expected==records['compile-'+label],'Compile/math recipe differs: '+label)
    parent=next(r['argv'] for r in read(build.GQA6/'commands.json') if r['label']=='link')
    require(sum(v==str(build.GQA6/'1.o') for v in parent)==1 and str(build.NATIVE/'17.o') in parent,
            'Uninstrumented original Output-Tile object missing')
    expected=[str(BUILD/'caller.o') if v==str(build.GQA6/'1.o') else remap(v) for v in parent]
    expected.insert(expected.index('-Wl,--gc-sections'),str(BUILD/'probe.o'))
    expected[expected.index('-o')+1]=str(BUILD/'output_phase.elf')
    expected=['-Wl,-Map='+str(BUILD/'link.map') if v.startswith('-Wl,-Map=') else v for v in expected]
    require(expected==records['link'],'Baseline object reuse/link recipe differs')
    return dict(observation_insertions=10,source_files_replayed=len(generated),compile_recipes_replayed=2,
                reused_objects=16,original_output_tile_object_retained=True,link_recipe_replayed=True,
                binding_nested=True,original_math_callback_and_schedule_text_retained=True)


def collect(output):
    output=Path(output).absolute()
    require(output==output.resolve() and output.is_relative_to(RUNS),'Fresh sole-verification output required')
    output.mkdir(parents=True,exist_ok=False)
    pins={};cache={};result=dict(state='ATTENTION_PHASE_COLLECTION_FAIL',simulation_launched=False,isa_launched=False,
        whole_model=False,default_f16_primary_path=False,optimization_speedup_claim=False)
    def pin(path,expected=None):
        path=Path(path).resolve(strict=True);key=str(path)
        actual=cache.get(key)
        if actual is None:actual=digest(path);cache[key]=actual
        require(expected is None or actual==expected,'Evidence/source identity mismatch: '+key)
        require(key not in pins or pins[key]==actual,'Conflicting evidence identity: '+key);pins[key]=actual
    try:
        pin(WORKER/'result.json',WORKER_SHA);worker=read(WORKER/'result.json');admit_worker(worker)
        require(not (WORKER/'early-failure.json').exists(),'Original worker early failure exists')
        pin(WORKER/'source-pins.json',WORKER_PINS_SHA);worker_pins=read(WORKER/'source-pins.json')
        for group in (worker_pins,worker['artifacts'],worker['image_pins']):
            for path,expected in group.items():pin(path,expected)
        pin(BUILD/'build.json',BUILD_SHA);program=read(BUILD/'build.json');admit_build(program)
        pin(BUILD/'source-pins.json',program['source_pins_sha256'])
        for group in (read(BUILD/'source-pins.json'),program['artifacts']):
            for path,expected in group.items():pin(path,expected)
        pin(program['elf'],ELF_SHA);pin(program['golden'],worker_pins[str(Path(program['golden']).resolve())])
        require(worker_pins.get(str(BUILD/'build.json'))==BUILD_SHA and
                any(v==worker['prerequisite_result_sha256'] for v in worker_pins.values()),'Worker build/prerequisite binding differs')
        commands=read(WORKER/'commands.json')
        require([r['label'] for r in commands]==['RUNNING','PROTOCOL'] and all(r['returncode']==0 for r in commands),
                'Original execution/protocol completion differs')
        require(commands[0]['argv'][0]==worker['simv'] and commands[0]['argv'].count('+PRELOAD='+program['elf'])==1,
                'Simulation/ELF command binding differs')
        for flag in ('--require-events','--require-backend','--require-axi','--require-axi-write'):
            require(commands[1]['argv'].count(flag)==1,'Original protocol gate missing')
        sys.path.insert(0,str(HERE));sys.path.insert(0,str(VERIFY/'verification'))
        source=source_replay()
        from run_wide_soc_smoke import elf_admission,check_platform
        require(elf_admission(Path(program['elf']).read_bytes(),16)==worker['preload_segments'],'Physical128 ELF admission differs')
        work=WORKER/'work';text=(work/'run.vcs.log').read_text()
        measured,summary=numerical_replay(text,Path(program['golden']).read_bytes(),worker)
        platform=check_platform(text,128);require(platform==worker['platform'],'Platform trace replay differs')
        from ara_verify.uvm_dut import check_real_uvm_log
        from ara_verify.artifacts import simulation_image
        protocol=check_real_uvm_log(work/'run.vcs.log',require_events=True,require_backend=True,
                    require_axi=True,require_axi_write=True,vector_trace=work/'vector_trace.csv')
        protocol.update(simv_sha256=digest(worker['simv']),elf_sha256=ELF_SHA,
                        sim_image_sha256=simulation_image(Path(worker['simv'])))
        protocol_agreement(protocol,read(work/'uvm_result.json'),worker)
        (output/'protocol-replay.json').write_text(json.dumps(protocol,indent=2)+'\n')
        (output/'source-replay.json').write_text(json.dumps(source,indent=2)+'\n')
        tests=importlib.import_module('test_collect_attention_phase');stream=io.StringIO()
        tested=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        (output/'unit-tests.log').write_text(stream.getvalue())
        require(tested.wasSuccessful() and tested.testsRun==7,'Collector admission/raw replay negative tests failed')
        for module in tuple(sys.modules.values()):
            name=getattr(module,'__file__',None)
            if name and Path(name).is_file():
                path=Path(name).resolve()
                if any(path.is_relative_to(root) for root in (ROOT,VERIFY)):
                    require(str(path) in worker_pins or path in (Path(__file__).resolve(),HERE/'test_collect_attention_phase.py'),
                            'Replay helper not in original frozen inventory: '+str(path));pin(path,worker_pins.get(str(path)))
        for path in (Path(__file__),HERE/'test_collect_attention_phase.py',Path(sys.executable)):pin(path)
        for path,expected in pins.items():require(digest(path)==expected,'Post-replay source/evidence drift: '+path)
        (output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        compact=dict(state='QUANTIZED_ATTENTION_PHASE_SCOPED_ACCEPTANCE_INDEPENDENTLY_REPLAYED',
            collector=str(output/'result.json'),run=str(WORKER),result_sha256=WORKER_SHA,elf_sha256=ELF_SHA,
            summary=summary,protocol_replayed=True,paired_bitexact=True,csr_bitexact=True,
            scope='Captured Qwen2.5 GQA6 D128 visible128 one-group complete quantized Attention calls',
            coefficient_scope='expf plus max/sum recurrence and coefficient writes, not pure exp',
            pv_scope='V decoding plus PV accumulation',whole_model=False,default_f16_primary_path=False,
            optimization_speedup_claim=False)
        (output/'compact-evidence.json').write_text(json.dumps(compact,indent=2)+'\n')
        result.update(state=compact['state'],worker_result_sha256=WORKER_SHA,build_result_sha256=BUILD_SHA,
            elf_sha256=ELF_SHA,measured=measured,summary=summary,platform=platform,source_replayed=source,
            independent_protocol_replayed=True,worker_inputs_checked=len(worker_pins),worker_artifacts_checked=len(worker['artifacts']),
            build_artifacts_checked=len(program['artifacts']),unit_tests_passed=tested.testsRun,
            post_pins_match=True,source_pins_sha256=digest(output/'source-pins.json'),
            limits=['Observation-only quantized Qwen2.5 call; not default F16/Qwen3 path, full node or whole-model speedup',
                    'Internal serialization/code layout perturbation is measured, not an optimization speedup',
                    'Coefficient phase is not pure exp; PV includes decode; binding is nested in QK and not additive',
                    'Unobserved time is distinct from all remaining phases; no per-operation or per-exp extrapolation',
                    'No new execution, MMU/PMP, synthesis, area or production-backend acceptance'])
    except BaseException as exc:result.update(error=repr(exc),post_pins_match=False);raise
    finally:
        if not (output/'source-pins.json').exists():(output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='result.json'}
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT)
    result=collect(p.parse_args().output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('artifacts','measured','platform')},indent=2))
