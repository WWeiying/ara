#!/usr/bin/env python3
"""One frozen 256-bit-ingress original/off/balanced compute experiment."""
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
from run_wide_compute import HERE, ROOT, RUNS, SOURCES
from run_mixed_compute import (PARENT, PARENT_SHA, EXPANDED, EXPANDED_SHA, EDGES,
    EDGES_SHA, SCALE_SHA, VECTOR_SHA, OLD_VECTOR_SHA, TB_SHA, pin, accepted, bound_vectors)
from balanced_dot_source import dot, decoder
from balanced_integer_source import integer
from balanced_compute_source import accumulator, compute
from balanced_compute_fixture import fixture
import check_balanced_compute as checker

TESTS=('test_balanced_dot_source','test_balanced_integer_source','test_balanced_compute_source',
       'test_balanced_compute_fixture','test_check_balanced_compute','test_run_balanced_compute')
TRANSFORMS={'qbs_dot_array':dot,'qbs_profile_decoder':decoder,'qbs_profile_engine_int':integer,
            'qbs_fp_accumulator':accumulator,'qbs_compute_engine':compute}


def run(output, execute):
    require(execute,'Explicit reviewed execution required')
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS),'Sole verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[]
    result=dict(state='PREPARING',production_rtl_changed=False,soc_integrated=False,
                whole_model=False,physical_ingress_bits=256,area_measured=False,synthesis_run=False)
    def save(name,value):
        with (out/name).open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    def command(argv,label,bound):
        argv=list(map(str,argv));pin(pins,argv[0]);verify_pins(pins)
        row=dict(argv=argv,label=label,timeout_seconds=bound);commands.append(row)
        result['state']=label
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
        parent,parent_pins=accepted(pins,PARENT,PARENT_SHA,'WIDE_WEIGHT_COMPUTE_PAIR_PASS')
        expanded,expanded_pins=accepted(pins,EXPANDED,EXPANDED_SHA,'FP16_FP32_EXPANDED_SCALE_COMPONENT_PASS')
        edge,_=accepted(pins,EDGES,EDGES_SHA,'MIXED_SCALE_EDGE_HOST_ORACLES_PREPARED_NOT_RTL_VERIFIED')
        require(parent['post_pins_match'] and expanded['post_pins_match'] and edge['old_suite_body_byte_identical'],
                'Unaccepted source/arithmetic/vector predecessor')
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE):pin(pins,path)
        for name in (*TESTS,'test_wide_compute','test_mixed_scale_edge_vectors','mixed_scale_edge_vectors'):
            pin(pins,HERE/(name+'.py'))
        pin(pins,Path(__file__));pin(pins,sys.executable)
        original=EDGES/'combined-matrix1-76.txt';pin(pins,original,VECTOR_SHA)
        old=PARENT/'vectors-matrix1.txt';pin(pins,old,OLD_VECTOR_SHA)
        shapes=bound_vectors(old.read_text(),(EDGES/'extras-native.txt').read_text(),original.read_text())
        candidate=out/'vectors-balanced.txt';candidate.write_text(checker.vector(original.read_text()));pin(pins,candidate)
        source=out/'source';source.mkdir();source_paths=[];transforms={}
        for path in SOURCES:
            old=PARENT/'source-snapshot'/path.name;pin(pins,old,parent_pins[str(old)])
            target=source/path.name;shutil.copyfile(old,target);pin(pins,target);source_paths.append(target)
        includes=ROOT/'hardware/deps/common_cells/include'
        for path in includes.rglob('*.svh'):
            pin(pins,path,parent_pins[str(path.resolve())]);target=source/'include'/path.relative_to(includes)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);pin(pins,target)
        for name,transform in TRANSFORMS.items():
            generated,report=transform((source/(name+'.sv')).read_text())
            target=source/(name+'_balanced.sv');target.write_text(generated);pin(pins,target)
            source_paths.append(target);transforms[name]=report
        for name,sha in SCALE_SHA.items():
            old=EXPANDED/'src'/name;pin(pins,old,expanded_pins[str(old)])
            require(digest(old)==sha,'Accepted arithmetic changed')
            target=source/name;shutil.copyfile(old,target);pin(pins,target);source_paths.append(target)
        tb=PARENT/'source-snapshot/qbs_wide_compute_tb.sv';pin(pins,tb,TB_SHA)
        fixtures=[]
        for clone in (0,1):
            text,report=fixture(tb.read_text(),clone)
            directory=source/('clone' if clone else 'original');directory.mkdir()
            target=directory/'qbs_balanced_compute_tb.sv';target.write_text(text);pin(pins,target)
            fixtures.append(target);transforms['fixture-'+str(clone)]=report
        save('transforms.json',transforms)
        save('fixture.json',dict(count=76,original=original.as_posix(),original_sha256=VECTOR_SHA,
            candidate_sha256=digest(candidate),only_candidate_capacity_dot_counters_differ=True,
            unchanged_outputs_flags_payloads=True,additional_fault_case=1,
            shapes=[{k:v for k,v in s.items() if k!='outputs'} for s in shapes],
            balanced_shapes=[{k:v for k,v in s.items() if k!='outputs'} for s in checker.candidate_shapes(shapes)]))
        command([sys.executable,'-B','-m','unittest',*TESTS,'-v'],'unit-tests',120)
        vcs=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
        pin(pins,vcs);pin(pins,vcs.parent.parent/'linux64/bin/vcs1')
        save('source-pins-precompile.json',pins)
        logs=[];images=[]
        for label,clone,mode in (('original',0,0),('disabled',1,0),('enabled',1,1)):
            build=out/label;build.mkdir();image=build/'simv'
            command([vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext',
                '+incdir+'+str(source/'include'),*source_paths,fixtures[clone],
                '-top','qbs_balanced_compute_tb','-pvalue+qbs_balanced_compute_tb.Wide=1',
                '-pvalue+qbs_balanced_compute_tb.Balanced='+str(mode),
                '-Mdir='+str(build/'csrc'),'-o',image],'compile-'+label,600)
            pin(pins,image);libraries=list(build.rglob('*.so'));require(libraries,'VCS library missing')
            for path in libraries:pin(pins,path)
            images.append(image)
            selected=candidate if mode else original
            logs.append(command([image,'-no_save','+QBS_COMMAND_VECTOR_FILE='+str(selected)],'run-'+label,300))
        measured=checker.check(*logs,original.read_text(),candidate.read_text())
        for cid in (74,75):
            row=measured['cases'][cid]['candidate_fp']
            require(row['mixed_issue']==row['mixed_return']==row['mixed_nx']==64,'NX-only discriminator lost')
        fault=command([images[-1],'-no_save','+QBS_COMMAND_VECTOR_FILE='+str(candidate),
                       '+MC_FAULT_ONLY'],'run-balanced-faults',300)
        faults=checker.fault_check(fault,original.read_text(),logs[0])
        save('measured.json',measured);save('fault-measured.json',faults)
        verify_pins(pins)
        result.update(state='BALANCED_COMPUTE_ORDER_FLAGS_WORK_DISABLED_AND_FAULTS_PASS',
            post_pins_match=True,normal_per_image=76,recovery_per_image=5,faults_per_image=5,
            extra_faults=3,extra_recoveries=3,disabled_cycle_identical=True,
            m1_m2_and_short_format_timing_identical=True,per_accumulator_fp_order_equal=True,
            mixed_issues=measured['mixed_issues'],mixed_nx=measured['mixed_nx'],
            last_correction_issues=measured['last_correction_issues'],
            limits=measured['limits']+['No reader/MMU, SDK/GGML, SoC or whole-model acceptance'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc),first_failure_preserved=True)
    finally:
        try:verify_pins(pins)
        except Exception as exc:result.update(state='FAIL',post_pins_match=False,pin_error=repr(exc))
        save('commands.json',commands);save('source-pins.json',pins)
        result['source_pins_sha256']=digest(out/'source-pins.json')
        result['artifacts']={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name!='status.json'}
        save('result.json',result)
    print(json.dumps(dict(state=result['state'],output=str(out),error=result.get('error'),
                          result_sha256=digest(out/'result.json'))))
    return 0 if result['state']=='BALANCED_COMPUTE_ORDER_FLAGS_WORK_DISABLED_AND_FAULTS_PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();sys.exit(run(args.output,args.execute_reviewed))
