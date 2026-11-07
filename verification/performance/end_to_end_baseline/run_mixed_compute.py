#!/usr/bin/env python3
"""Bounded original/off/on compute experiment using accepted native vectors."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from run_wide_compute import HERE, ROOT, RUNS, SOURCES, parse_vectors
from mixed_accumulator_source import accumulator, compute, ACC_SHA, COMPUTE_SHA
from mixed_compute_fixture import fixture
from mixed_scale_edge_vectors import append_vectors, matrix_vectors, parse_extras
from check_mixed_compute import check, fault_check

PARENT = RUNS/'e2e_wide_compute_20261106_01'
EXPANDED = RUNS/'e2e_mixed_scale_expanded_20261106_01'
EDGES = RUNS/'e2e_mixed_scale_edges_20261106_01'
PARENT_SHA = '8badb69f8ca82f5a31ce0e601622a90944d5e3da9a418bc014e3dae5cfaed577'
EXPANDED_SHA = 'd68fad17f1a5812cfd5e725cd29824228adfa898e0efb7c28704710d60d39cc9'
EDGES_SHA = '7bede0e75550725d6755f680e7d296ed7c913b6c49d5fca60f2fd3d65357440a'
VECTOR_SHA = 'c6d9833200688951b4653104a2d9d7caf4abba5f97186418f0060e71e067d804'
OLD_VECTOR_SHA = 'dc1ab0b04a27766ecda5bdc09eb589f566e77faecd52ac9e764f8bd47d00c883'
TB_SHA = 'db5c93567aa6f648af4a6af1fb1926760e20be65f25e9fa72499e0adbb96d3de'
SCALE_SHA = {
    'qbs_mixed_scale.sv':'66a77cd915eb8d973fb6c93d8bb12e237da5175324eb0160dc29f3fd30f55dda',
    'qbs_fp16_f32_scale.sv':'b46647cbe94b5e200fca09e1513b14f58b8009815777a5d2e7fb033bad6293b9',
}


def pin(pins, path, expected=None):
    path=Path(path).resolve(strict=True);actual=digest(path)
    require(expected is None or actual==expected,'Input identity differs: '+str(path))
    require(str(path) not in pins or pins[str(path)]==actual,'Input drift: '+str(path))
    pins[str(path)]=actual


def accepted(pins, root, expected, state):
    pin(pins,root/'result.json',expected)
    report=json.loads((root/'result.json').read_text())
    require(report['state']==state,'Predecessor not accepted: '+str(root))
    pin(pins,root/'source-pins.json',report['source_pins_sha256'])
    old=json.loads((root/'source-pins.json').read_text())
    # Explicitly bind files subsequently consumed; do not depend on old images.
    for name,sha in report.get('artifacts',{}).items():
        if Path(name).name in ('vectors-matrix1.txt','combined-matrix1-76.txt',
                              'extras-native.txt','extras-matrix1.txt','cases.json'):
            pin(pins,name,sha)
    return report,old


def bound_vectors(old, extras, combined):
    require(digest_bytes(old)==OLD_VECTOR_SHA and digest_bytes(combined)==VECTOR_SHA,
            'Exact 66+10 vector identities required')
    parsed=parse_extras(extras)
    require(len(parsed)==10 and append_vectors(old,matrix_vectors(extras))==combined,
            'New vector list or retained original golden differs')
    shapes=parse_vectors(combined)
    require(len(shapes)==76 and {s['profile'] for s in shapes[:66]}==set(range(1,10)),
            'Missing original nine-profile coverage')
    require([(s['profile'],s['m'],s['n'],s['kb'],s['flags'],set(s['outputs'].values()))
             for s in shapes[-2:]]==[(2,4,8,2,1,{0}),(1,4,8,2,1,{0})],
            'NX-only Q6/Q4 discriminator fixtures required')
    return shapes


def digest_bytes(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def run(output, execute):
    require(execute,'Explicit reviewed execution required')
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS),'Sole verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[]
    result=dict(state='PREPARING',production_rtl_changed=False,soc_integrated=False,
                whole_model=False,area_measured=False,synthesis_run=False)
    def save(name,value):
        with (out/name).open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    def command(argv,label,bound):
        argv=list(map(str,argv));pin(pins,argv[0]);verify_pins(pins)
        row=dict(argv=argv,label=label,timeout_seconds=bound);commands.append(row)
        result['state']=label
        (out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
        with (out/(label+'.log')).open('xb') as stream:
            child=subprocess.Popen(argv,cwd=out,stdout=stream,stderr=subprocess.STDOUT,
                                   env=env,start_new_session=True)
            result['child_pid']=child.pid
            (out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
            try:code=child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid,signal.SIGKILL);child.wait();raise
        result['child_pid']=None;row['returncode']=code;verify_pins(pins)
        text=(out/(label+'.log')).read_text()
        require(code==0 and not re.search(r'Fatal:|Error[-:]|Assertion.*failed|UVM_(?:FATAL|ERROR)',text),
                'First failure preserved: '+label)
        return text
    env={k:v for k,v in os.environ.items() if k not in (
        'LD_PRELOAD','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','COMPILER_PATH','GCC_EXEC_PREFIX','LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin',PYTHONPATH=str(HERE),LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
    try:
        _,parent_pins=accepted(pins,PARENT,PARENT_SHA,'WIDE_WEIGHT_COMPUTE_PAIR_PASS')
        expanded,expanded_pins=accepted(pins,EXPANDED,EXPANDED_SHA,'FP16_FP32_EXPANDED_SCALE_COMPONENT_PASS')
        edge,_=accepted(pins,EDGES,EDGES_SHA,'MIXED_SCALE_EDGE_HOST_ORACLES_PREPARED_NOT_RTL_VERIFIED')
        require(expanded['post_pins_match'] and edge['old_suite_body_byte_identical'],
                'Unverified arithmetic or vector predecessor')
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE):pin(pins,path)
        for name in ('test_check_mixed_compute.py','test_mixed_accumulator_source.py',
                     'test_mixed_scale_edge_vectors.py','test_wide_compute.py','test_run_mixed_compute.py'):
            pin(pins,HERE/name)
        pin(pins,Path(__file__));pin(pins,sys.executable)
        oldpath=PARENT/'vectors-matrix1.txt';pin(pins,oldpath,OLD_VECTOR_SHA)
        vectors=EDGES/'combined-matrix1-76.txt';pin(pins,vectors,VECTOR_SHA)
        shapes=bound_vectors(oldpath.read_text(),(EDGES/'extras-native.txt').read_text(),vectors.read_text())
        source=out/'source';source.mkdir();source_paths=[]
        for path in SOURCES:
            original=PARENT/'source-snapshot'/path.name
            pin(pins,original,parent_pins[str(original)])
            target=source/path.name;shutil.copyfile(original,target);pin(pins,target)
            source_paths.append(target)
        includes=ROOT/'hardware/deps/common_cells/include'
        for path in includes.rglob('*.svh'):
            pin(pins,path,parent_pins[str(path.resolve())]);target=source/'include'/path.relative_to(includes)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);pin(pins,target)
        transforms={}
        for name,transform,sha in (('qbs_fp_accumulator',accumulator,ACC_SHA),
                                   ('qbs_compute_engine',compute,COMPUTE_SHA)):
            original=source/(name+'.sv');require(digest(original)==sha,'Controller source drift')
            generated,report=transform(original.read_text())
            target=source/(name+'_mixed.sv');target.write_text(generated);pin(pins,target)
            source_paths.append(target);transforms[name]=report
        for name,sha in SCALE_SHA.items():
            original=EXPANDED/'src'/name;pin(pins,original,expanded_pins[str(original)])
            require(digest(original)==sha,'Accepted arithmetic identity changed')
            target=source/name;shutil.copyfile(original,target);pin(pins,target);source_paths.append(target)
        original_tb=PARENT/'source-snapshot/qbs_wide_compute_tb.sv';pin(pins,original_tb,TB_SHA)
        fixtures=[]
        for clone in (0,1):
            text,report=fixture(original_tb.read_text(),clone)
            directory=source/('clone' if clone else 'original');directory.mkdir()
            target=directory/'qbs_mixed_compute_tb.sv';target.write_text(text);pin(pins,target)
            fixtures.append(target);transforms['fixture-'+str(clone)]=report
        save('transforms.json',transforms)
        save('fixture.json',dict(count=76,original_cases=66,new_cases=10,
             old_body_unchanged=True,nx_only_cases=[74,75],vector_sha256=VECTOR_SHA,
             real_input_scope='Inherited Qwen2.5 Prefill M1/M4 slices; not current-model Decode',
             shapes=[{k:v for k,v in shape.items() if k!='outputs'} for shape in shapes]))
        command([sys.executable,'-B','-m','unittest','test_check_mixed_compute',
                 'test_mixed_accumulator_source','test_mixed_scale_edge_vectors',
                 'test_run_mixed_compute','-v'],'unit-tests',90)
        vcs=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
        pin(pins,vcs);pin(pins,vcs.parent.parent/'linux64/bin/vcs1')
        save('source-pins-precompile.json',pins)
        logs=[];images=[]
        for label,clone,mixed in (('original',0,0),('disabled',1,0),('enabled',1,1)):
            build=out/label;build.mkdir();image=build/'simv'
            command([vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext',
                     '+incdir+'+str(source/'include'),*source_paths,fixtures[clone],
                     '-top','qbs_mixed_compute_tb','-pvalue+qbs_mixed_compute_tb.Wide=0',
                     '-pvalue+qbs_mixed_compute_tb.Mixed='+str(mixed),
                     '-Mdir='+str(build/'csrc'),'-o',image],'compile-'+label,600)
            pin(pins,image);libraries=list(build.rglob('*.so'));require(libraries,'VCS library missing')
            for path in libraries:pin(pins,path)
            images.append(image)
            logs.append(command([image,'-no_save','+QBS_COMMAND_VECTOR_FILE='+str(vectors)],'run-'+label,300))
        measured=check(*logs,vectors.read_text())
        for cid in (74,75):
            row=measured['cases'][cid]['physical']
            require(row['mixed_issue']==row['mixed_return']==row['mixed_nx']==64,
                    'NX-only discriminator did not exercise exactly 64 new returns')
        fault=command([images[-1],'-no_save','+QBS_COMMAND_VECTOR_FILE='+str(vectors),
                       '+MC_FAULT_ONLY'],'run-mixed-faults',300)
        faults=fault_check(fault,vectors.read_text(),logs[0])
        save('measured.json',measured);save('fault-measured.json',faults)
        verify_pins(pins)
        result.update(state='MIXED_SCALE_COMPUTE_ORDER_FLAGS_DISABLED_CYCLES_AND_DRAIN_PASS',
            post_pins_match=True,normal_per_image=76,recovery_per_image=5,faults_per_image=5,
            extra_mixed_faults=2,extra_recovery_commands=2,disabled_cycle_identical=True,
            numerical_outputs_and_flags_equal=True,per_accumulator_operation_order_equal=True,
            mixed_issues=measured['mixed_issues'],mixed_nx=measured['mixed_nx'],
            simultaneous_returns=measured['simultaneous_returns'],
            predecessor_sha256=dict(compute=PARENT_SHA,arithmetic=EXPANDED_SHA,edges=EDGES_SHA),
            limits=measured['limits']+['No reader, MMU, full controller, SDK, or whole-model acceptance'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc),first_failure_preserved=True)
    finally:
        try:verify_pins(pins)
        except Exception as exc:result.update(state='FAIL',post_pins_match=False,pin_error=repr(exc))
        save('commands.json',commands);save('source-pins.json',pins)
        result['source_pins_sha256']=digest(out/'source-pins.json')
        result['artifacts']={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name!='status.json'}
        save('result.json',result)
    print(json.dumps(dict(state=result['state'],output=str(out),error=result.get('error'),
                          result_sha256=digest(out/'result.json'))))
    return 0 if result['state']=='MIXED_SCALE_COMPUTE_ORDER_FLAGS_DISABLED_CYCLES_AND_DRAIN_PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();sys.exit(run(args.output,args.execute_reviewed))
