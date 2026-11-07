#!/usr/bin/env python3
"""Host-only independent replay of the frozen RMS output worker; never launches EDA/Spike."""
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
WORKER=RUNS/'e2e_rms_vector_output_vcs_20261106_01'
WORKER_SHA='8470bc66e5f1f0199b5d1fcd0e775a48dd2e0a38bccc368a0debba885c9b2127'
WORKER_PINS_SHA='a46ba7cd52c14377b5b4ee2462a252515d3ea4122f538f46b82be3a1ed7bb37f'
BUILD=RUNS/'e2e_rms_vector_output_build_20261106_01'
BUILD_SHA='5bfba71c500ab47e6633887f66cac8bd356e4c08cfe633b05c220ab29b2b6f15'
ELF_SHA='dca9f7c24dc84463babc317c670165c243cfa2d6493f1f0c0b03ef9f02a32884'
OUT=RUNS/'e2e_rms_vector_output_collect_20261106_01'


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def admit_worker(record):
    require(record.get('state')=='REAL_FUSED_RMS_VECTOR_OUTPUT_RTL_PASS' and record.get('child_pid') is None and
            all(record.get(k) is True for k in ('performance_measured','independent_protocol_checked','post_pins_match')) and
            all(record.get(k) is False for k in ('whole_model','rtl_changed','production_library_changed','synthesis_run')),
            'Terminal scoped RTL PASS required')
    require(record.get('source_pins_sha256')==WORKER_PINS_SHA and record.get('elf_sha256')==ELF_SHA and
            record.get('elf')==str(BUILD/'rms_output.elf'),'Exact worker/build identity required')


def admit_build(program):
    expected=dict(state='REAL_FUSED_RMS_VECTOR_OUTPUT_BUILT_NOT_EXECUTED',rows=[1,4],width=2048,
                  trials=8,outputs_checked=40960,boundary_cases=53,sum_cases=10,output_boundary_cases=155,
                  order=[0,1,1,0],recompiled_objects=4,reused_objects=12,elf_sha256=ELF_SHA)
    require(all(program.get(k)==v for k,v in expected.items()) and
            program.get('baseline_arithmetic_unchanged') is True and program.get('timing_includes_csr_completion') is True and
            all(program.get(k) is False for k in ('rtl_changed','production_library_changed','whole_model','performance_measured')),
            'Exact accepted four-object output build required')


def numerical_replay(rtl,isa,trace,prefill,decode,worker):
    # Execute the sealed checker on RAW evidence, not its recorded summary.
    import check_rms_output as check
    from check_projection_native import fields
    measured=check.check(rtl,prefill,decode)
    reference=check.check(isa,prefill,decode)
    signature=check.signature(reference)
    exits=[fields(line,'SPIKE_SOC_EXIT') for line in isa.replace('\r','').splitlines() if line.startswith('SPIKE_SOC_EXIT ')]
    require(len(exits)==1 and set(exits[0])=={'status','uart_bytes'} and exits[0]['status']==0 and exits[0]['uart_bytes']>0,
            'Complete successful Spike exit required')
    require(check.signature(measured)==signature==worker['isa_signature'],'Spike/RTL/checker signature differs')
    activity=check.activity(trace)
    require(measured==worker['measured'] and activity==worker['activity'],'Raw numerical/activity replay differs from receipt')
    return measured,signature,activity


def protocol_agreement(replayed,recorded,worker):
    require(replayed==recorded and replayed.get('status')=='PASS' and replayed.get('issues')==[],
            'Complete raw protocol replay must equal producer protocol, not just PASS')
    require(replayed.get('elf_sha256')==ELF_SHA and replayed.get('sim_image_sha256')==worker['image_pins'],
            'Protocol ELF/image identity differs')


def commands_agreement(commands,worker):
    require([r.get('label') for r in commands]==['ISA_REFERENCE','SIMULATION','PROTOCOL'] and
            all(r.get('returncode')==0 for r in commands),'Original ISA/simulation/protocol completion required')
    require(commands[0]['argv'].count(worker['elf'])==1 and commands[1]['argv'][0]==worker['simv'] and
            commands[1]['argv'].count('+PRELOAD='+worker['elf'])==1 and
            commands[1]['argv'].count('+TESTCASE=rms_guarded_output_abba')==1,'Original command/ELF binding differs')
    for flag in ('--require-events','--require-backend','--require-axi','--require-axi-write'):
        require(commands[2]['argv'].count(flag)==1,'Original protocol gate missing: '+flag)


def replace_object(argv,old,new):
    require(argv.count(str(old))==1,'Exact one-member object replacement required')
    return [str(new) if item==str(old) else item for item in argv]


def source_replay(program,pin):
    from rms_norm_output_source import candidate,caller
    from rms_norm_completion import completed_caller
    from build_rms_norm_native import link_archives
    parent=Path(program['parent_build']);prior=read(parent/'build.json')
    require(prior['state']=='REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED' and
            prior['captured_output_replay_bitwise'] and prior['timing_includes_csr_completion'] and
            program['parent_elf_sha256']==prior['elf_sha256'],'Original captured-output baseline admission missing')
    pin(parent/'build.json');pin(parent/'source-pins.json',prior['source_pins_sha256'])
    for group in (read(parent/'source-pins.json'),prior['artifacts']):
        for path,sha in group.items():pin(path,sha)
    arithmetic=Path(prior['parent_build'])
    original_commands={r['label']:r['argv'] for r in read(arithmetic/'commands.json')}
    parent_commands={r['label']:r['argv'] for r in read(parent/'commands.json')}
    new_commands={r['label']:r['argv'] for r in read(BUILD/'commands.json')}
    inventory=read(BUILD/'source-pins.json')
    ops=[Path(path) for path in inventory if path.endswith('/llama/ggml/src/ggml-cpu/ops.cpp')]
    require(len(ops)==1,'Exact original GGML ops source required')
    source=ops[0].read_text()
    require((parent/'completed.cpp').read_text()==completed_caller((HERE/'rms_norm_native.cpp').read_text()),
            'Actual completed-state parent caller source differs')
    generated={'candidate':candidate(source),'strict-candidate':candidate(source,'strict_candidate'),
               'main':caller((parent/'completed.cpp').read_text())}
    for name,text in generated.items():require((BUILD/(name+'.cpp')).read_text()==text,'Source transform replay differs: '+name)
    for name in ('candidate','strict-candidate','main','output-checks'):
        template=list(parent_commands['compile-main'] if name in ('main','output-checks') else original_commands['compile-'+name])
        path=HERE/'rms_output_checks.cpp' if name=='output-checks' else BUILD/(name+'.cpp')
        template[template.index('-c')+1]=str(path);template[template.index('-o')+1]=str(BUILD/(name+'.o'))
        if name=='output-checks':template+=['-frounding-math','-fno-tree-vectorize','-ffp-contract=off']
        require(template==new_commands['compile-'+name],'Compiler/math recipe changed: '+name)
    link=list(parent_commands['link'])
    for name in ('main','candidate','strict-candidate'):
        link=replace_object(link,(parent if name=='main' else arithmetic)/(name+'.o'),BUILD/(name+'.o'))
    link.insert(link.index('-Wl,--gc-sections'),str(BUILD/'output-checks.o'))
    link[link.index('-o')+1]=str(BUILD/'rms_output.elf')
    link=['-Wl,-Map='+str(BUILD/'link.map') if value.startswith('-Wl,-Map=') else value for value in link]
    require(link==new_commands['link'],'Original baseline/reused object/link recipe changed')
    require(link_archives((BUILD/'link.map').read_text(),prior['runtime_archives'])==program['linked_archives'],
            'Actual runtime archive selection differs')
    return dict(generated_sources={name:digest(BUILD/(name+'.cpp')) for name in generated},
                parent_captured_output_replay_bitwise=True,completion_caller_replayed=True,
                math_compile_recipes_replayed=4,link_recipe_replayed=True,recompiled_objects=4,reused_objects=12)


def collect(output):
    output=Path(output).absolute()
    require(output==output.resolve() and output.is_relative_to(RUNS),'Fresh sole-verification collection output required')
    output.mkdir(parents=True,exist_ok=False)
    pins={};cache={}
    result=dict(state='RMS_OUTPUT_COLLECTION_FAIL',simulation_launched=False,isa_launched=False,
                whole_model=False,rtl_changed=False,production_library_changed=False)
    def pin(path,expected=None):
        path=Path(path).resolve(strict=True);key=str(path)
        actual=cache.get(key)
        if actual is None:actual=digest(path);cache[key]=actual
        require(expected is None or actual==expected,'Evidence/source identity mismatch: '+key)
        require(key not in pins or pins[key]==actual,'Conflicting evidence identity: '+key)
        pins[key]=actual
    try:
        pin(WORKER/'result.json',WORKER_SHA);worker=read(WORKER/'result.json');admit_worker(worker)
        pin(WORKER/'source-pins.json',WORKER_PINS_SHA);worker_pins=read(WORKER/'source-pins.json')
        for group in (worker_pins,worker['artifacts'],worker['image_pins']):
            for path,sha in group.items():pin(path,sha)
        pin(BUILD/'build.json',BUILD_SHA);program=read(BUILD/'build.json');admit_build(program)
        pin(BUILD/'source-pins.json',program['source_pins_sha256'])
        for group in (read(BUILD/'source-pins.json'),program['artifacts']):
            for path,sha in group.items():pin(path,sha)
        pin(program['elf'],ELF_SHA)
        require(worker_pins.get(str(BUILD/'build.json'))==BUILD_SHA,'Worker did not bind accepted output build')
        require(any(value==worker['prerequisite_result_sha256'] for value in worker_pins.values()),'Prerequisite receipt not in worker pins')
        sys.path.insert(0,str(HERE));sys.path.insert(0,str(VERIFY/'verification'))
        source=source_replay(program,pin)
        data=Path(program['data']);pin(data/'data.json');config=read(data/'data.json')
        require(config['schema_version']==2 and config['k']==2048 and config['rows']==4 and
                config['token_ids']==[32,4621,17654,51435] and config['decode_token']==22406,
                'Actual Prefill/Decode identity differs')
        pin(data/'source-pins.json',config['source_pins_sha256'])
        for group in (read(data/'source-pins.json'),config['artifacts']):
            for path,sha in group.items():pin(path,sha)
        for name,record in config['files'].items():
            require((data/name).stat().st_size==record['bytes'],'Tensor length differs: '+name);pin(data/name,record['sha256'])
        from run_wide_soc_smoke import elf_admission,check_platform
        require(elf_admission(Path(program['elf']).read_bytes(),16)==worker['preload_segments'],'ELF admission replay differs')
        require(program['preload_segments']['128']==worker['preload_segments'],'Build/worker preload differs')
        commands_agreement(read(WORKER/'commands.json'),worker)
        work=WORKER/'work';rtl=(work/'run.vcs.log').read_text();isa=(work/'isa_reference.log').read_text()
        measured,signature,activity=numerical_replay(rtl,isa,(work/'vector_trace.csv').read_text(),
            (data/'expected_f32.bin').read_bytes(),(data/'decode_expected_f32.bin').read_bytes(),worker)
        platform=check_platform(rtl,128);require(platform==worker['platform'],'Actual physical128 platform replay differs')
        from ara_verify.uvm_dut import check_real_uvm_log
        from ara_verify.artifacts import simulation_image
        protocol=check_real_uvm_log(work/'run.vcs.log',require_events=True,require_backend=True,
                    require_axi=True,require_axi_write=True,vector_trace=work/'vector_trace.csv')
        protocol.update(simv_sha256=digest(worker['simv']),elf_sha256=ELF_SHA,
                        sim_image_sha256=simulation_image(Path(worker['simv'])))
        protocol_agreement(protocol,read(work/'uvm_result.json'),worker)
        (output/'protocol-replay.json').write_text(json.dumps(protocol,indent=2)+'\n')
        (output/'source-replay.json').write_text(json.dumps(source,indent=2)+'\n')
        tests=importlib.import_module('test_collect_rms_output')
        suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
        stream=io.StringIO();tested=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        (output/'unit-tests.log').write_text(stream.getvalue())
        require(tested.wasSuccessful() and tested.testsRun==6,'Collector admission/raw-replay negative tests failed')
        for module in tuple(sys.modules.values()):
            filename=getattr(module,'__file__',None)
            if filename and Path(filename).is_file():
                path=Path(filename).resolve()
                if any(path.is_relative_to(root) for root in (ROOT,VERIFY)):
                    require(str(path) in worker_pins or path in (Path(__file__).resolve(),HERE/'test_collect_rms_output.py'),
                            'Replay helper absent from original frozen inventory: '+str(path))
                    pin(path,worker_pins.get(str(path)))
        for path in (Path(__file__),HERE/'test_collect_rms_output.py',Path(sys.executable)):pin(path)
        # The final pass rehashes, rather than relying on the first-pass cache.
        for path,expected in pins.items():require(digest(path)==expected,'Post-replay evidence drift: '+path)
        (output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        compact=dict(state='REAL_FUSED_RMS_VECTOR_OUTPUT_SCOPED_ACCEPTANCE_INDEPENDENTLY_REPLAYED',
            collector=str(output/'result.json'),run=str(WORKER),result_sha256=WORKER_SHA,
            source_pins_sha256=WORKER_PINS_SHA,elf_sha256=ELF_SHA,decode_call_speedup=measured['cases'][0]['call_speedup'],
            prefill4_call_speedup=measured['cases'][1]['call_speedup'],outputs_checked=40960,
            output_boundary_cases=155,boundary_cases=53,order_sensitive_sum_cases=10,
            timing_includes_csr_completion=True,independent_protocol_checked=True,whole_model=False,
            production_library_changed=False,rtl_changed=False)
        (output/'compact-evidence.json').write_text(json.dumps(compact,indent=2)+'\n')
        result.update(state='REAL_FUSED_RMS_VECTOR_OUTPUT_SCOPED_ACCEPTANCE_INDEPENDENTLY_REPLAYED',
            worker_result_sha256=WORKER_SHA,build_result_sha256=BUILD_SHA,elf_sha256=ELF_SHA,
            measured=measured,isa_signature=signature,activity=activity,platform=platform,
            independent_protocol_replayed=True,source_replayed=source,worker_inputs_checked=len(worker_pins),
            worker_artifacts_checked=len(worker['artifacts']),build_artifacts_checked=len(program['artifacts']),
            unit_tests_passed=tested.testsRun,
            post_pins_match=True,source_pins_sha256=digest(output/'source-pins.json'),
            limits=['Actual complete fused first-layer norm calls, not whole model speedup or GGML production promotion',
                    'Normal valid RAM, entry vstart=0, no memory-fault/intermediate-fflags equivalence',
                    'Reconstructed embedding inputs; exact captured outputs; prior baseline bitwise replay retained',
                    'Boundary cases are differential correctness checks, not extra real-model performance workloads',
                    'No new execution, synthesis, area or physical implementation acceptance'])
    except BaseException as exc:
        result.update(error=repr(exc),post_pins_match=False);raise
    finally:
        if not (output/'source-pins.json').exists():(output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result['artifacts']={str(path):digest(path) for path in sorted(output.iterdir()) if path.is_file() and path.name!='result.json'}
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args();result=collect(args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('artifacts','isa_signature','platform')},indent=2))
