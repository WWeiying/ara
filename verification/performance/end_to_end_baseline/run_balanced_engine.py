#!/usr/bin/env python3
"""Frozen original/off/on full-controller gate, before any new SoC build."""
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
from run_mixed_compute import pin
from run_wide_complete_engine import BASE, ORIGINAL, ROOT
from run_wide_compute import HERE, RUNS, parse_vectors
from matrix_dot_pair import candidate_vectors
from balanced_engine_source import engine
from balanced_engine_fixture import bench, wrapper
from check_balanced_compute import vector as balanced_vector
import check_balanced_engine as checker

BASE_SHA='fc937bdf96d44abac0d95eb14cd1bd974775afba2ec2c3a0fe47ceaa29c82b76'
COMPONENT=RUNS/'e2e_balanced_compute_20261106_01'
COMPONENT_SHA='a7ccf4376c736101c76659330999b633eed9985c943bc5cd5516bbc465a88b0d'
PRIOR=RUNS/'e2e_matrix_fault_schedule_20261106_02'
PRIOR_SHA='7c4ae2d5483bebb6b02c35b97370255d99d5ad1e75901925f30a0f29205bade2'
VECTOR_SHA={'matrix':'0df880f9f7d4e08ac1a3549caa913430254fd35eecabd38d7fad428a7ad0947f',
            'contexts':'7c25cf422fbef0432adabfb01426d805d35f3fd06515e51934414fc7f38c9d50'}
CLONES=tuple(name+'.sv' for name in ('qbs_dot_array_balanced','qbs_profile_decoder_balanced',
    'qbs_profile_engine_int_balanced','qbs_fp_accumulator_balanced','qbs_compute_engine_balanced',
    'qbs_mixed_scale','qbs_fp16_f32_scale'))
TESTS=('test_balanced_engine_source','test_balanced_engine_fixture','test_check_balanced_engine',
       'test_run_balanced_engine')


def run(output, execute):
    require(execute,'Explicit reviewed execution required')
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS),'Sole verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[]
    result=dict(state='PREPARING',production_rtl_changed=False,full_soc=False,
                whole_model=False,real_mmu_pmp=False,synthesis_run=False)
    def save(name,value):
        with (out/name).open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    def publish(): (out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    def command(argv,label,bound):
        argv=list(map(str,argv));pin(pins,argv[0]);verify_pins(pins)
        row=dict(label=label,argv=argv,timeout_seconds=bound);commands.append(row)
        result['state']=label
        with (out/(label+'.log')).open('xb') as stream:
            child=subprocess.Popen(argv,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            result['child_pid']=child.pid;publish()
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
    env.update(PATH='/usr/bin:/bin',PYTHONPATH=str(HERE),PYTHONDONTWRITEBYTECODE='1',LC_ALL='C')
    try:
        for root,sha in ((BASE,BASE_SHA),(COMPONENT,COMPONENT_SHA),(PRIOR,PRIOR_SHA)):
            pin(pins,root/'result.json',sha)
        base=json.loads((BASE/'result.json').read_text());component=json.loads((COMPONENT/'result.json').read_text())
        prior=json.loads((PRIOR/'result.json').read_text())
        require(base['state']=='DEFAULT_COMPLETE_QBS_ENGINE_CYCLES_UNCHANGED' and
                component['state']=='BALANCED_COMPUTE_ORDER_FLAGS_WORK_DISABLED_AND_FAULTS_PASS' and
                component['post_pins_match'],'Unaccepted controller/component source')
        inventories={}
        for root,report in ((BASE,base),(COMPONENT,component),(PRIOR,prior)):
            pin(pins,root/'source-pins.json',report['source_pins_sha256'])
            inventories[root]=json.loads((root/'source-pins.json').read_text())
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):pin(pins,path)
        for name in TESTS:pin(pins,HERE/(name+'.py'))
        pin(pins,Path(__file__));pin(pins,sys.executable)
        listing=BASE/'sources.log';pin(pins,listing,base['artifacts'][str(listing)])
        sources=[Path(line) for line in listing.read_text().splitlines()]
        require(sources and all(p.is_relative_to(ROOT) for p in sources),'Source graph escapes root')
        tree=out/'tree'
        for old in (BASE/'tree').rglob('*'):
            if not old.is_file():continue
            pin(pins,old,inventories[BASE][str(old)])
            target=tree/old.relative_to(BASE/'tree');target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(old,target);pin(pins,target)
        source_paths=[tree/p.relative_to(ROOT) for p in sources]
        for path in source_paths:require(path.is_file(),'Incomplete source graph')
        addition=tree/'balanced';addition.mkdir()
        for name in CLONES:
            old=COMPONENT/'source'/name;pin(pins,old,inventories[COMPONENT][str(old)])
            target=addition/name;shutil.copyfile(old,target);pin(pins,target);source_paths.append(target)
        ctl=tree/'hardware/src/vlsu/qbs/qbs_engine.sv'
        text,transform=engine(ctl.read_text());target=addition/'qbs_engine_balanced.sv'
        target.write_text(text);pin(pins,target);source_paths.append(target)
        recipes=dict(controller=transform);fixtures=[]
        for clone in (0,1):
            directory=tree/('clone' if clone else 'original');directory.mkdir()
            w,wr=wrapper((tree/'matrix_wrapper.sv').read_text(),clone)
            t,tr=bench((tree/'matrix_fault_suite.sv').read_text(),clone)
            wp=directory/'wrapper.sv';tp=directory/'bench.sv';wp.write_text(w);tp.write_text(t)
            pin(pins,wp);pin(pins,tp);fixtures.append((wp,tp));recipes[str(clone)]=dict(wrapper=wr,bench=tr)
        save('transforms.json',recipes)
        # The inherited include is a sealed simulation-only fault scheduler.
        probe=HERE/'matrix_replay_probe.svh';pin(pins,probe,inventories[BASE][str(probe)])
        experiment=tree/'experiment';experiment.mkdir();shutil.copyfile(probe,experiment/probe.name);pin(pins,experiment/probe.name)
        vectors={}
        for name,sha in VECTOR_SHA.items():
            old=ORIGINAL/(name+'-base.txt');pin(pins,old,sha)
            require(inventories[PRIOR].get(str(old))==sha,'Vector absent from accepted audit inventory')
            original=candidate_vectors(old.read_text());modified=balanced_vector(original)
            require(len(parse_vectors(original))==(36 if name=='matrix' else 12),'Vector inventory')
            paths=[]
            for mode,text in ((0,original),(1,modified)):
                target=out/f'{name}-{mode}.txt';target.write_text(text);pin(pins,target);paths.append(target)
            vectors[name]=paths
        save('fixtures.json',dict(physical_bits=256,matrix_dot=1,
             source_parent_sha256=BASE_SHA,compute_parent_sha256=COMPONENT_SHA,
             raw_vector_sha256=VECTOR_SHA,normal_per_image=72,context_direct_per_image=12,
             atomic_fault_classes=4,source_graph=[str(p) for p in source_paths]))
        command([sys.executable,'-B','-m','unittest',*TESTS,'-v'],'unit-tests',120)
        vcs=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
        pin(pins,vcs);pin(pins,vcs.parent.parent/'linux64/bin/vcs1')
        save('source-pins-precompile.json',pins)
        measured={}
        for label,clone,mode in (('original',0,0),('disabled',1,0),('enabled',1,1)):
            build=out/label;build.mkdir();image=build/'simv'
            includes=[tree/p for p in ('hardware/include','hardware/deps/common_cells/include',
                                      'hardware/deps/axi/include','experiment')]
            command([vcs,'-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext',
                *['+incdir+'+str(p) for p in includes],*source_paths,*fixtures[clone],'-top','qbs_engine_tb',
                '-pvalue+qbs_engine_tb.Wide=1','-pvalue+qbs_engine_tb.BusWidth=256',
                '-pvalue+qbs_engine_tb.Balanced='+str(mode),'-Mdir='+str(build/'csrc'),'-o',image],
                'compile-'+label,900)
            pin(pins,image);libraries=list(build.rglob('*.so'));require(libraries,'Missing VCS libraries')
            for path in libraries:pin(pins,path)
            measured[label]={}
            for name,gap in (('matrix',0),('matrix',3),('contexts',0)):
                vector=vectors[name][mode];extra=['+QBS_FUNCTIONAL_ONLY','+QBS_CONTEXT_SUITE'] if name=='contexts' else []
                text=command([image,'-no_save','+QBS_COMMAND_VECTOR_FILE='+str(vector),
                              '+QBS_RESPONSE_GAP='+str(gap),*extra],f'run-{label}-{name}-{gap}',600)
                measured[label][f'{name}-{gap}']=checker.check(text,vectors[name][0].read_text(),
                    vector.read_text(),clone,mode,gap,12 if name=='contexts' else 1)
        pairs={key:checker.pair(measured['original'][key],measured['disabled'][key],measured['enabled'][key])
               for key in measured['original']}
        save('measured.json',measured);save('paired.json',pairs);verify_pins(pins)
        result.update(state='BALANCED_COMPLETE_CONTROLLER_ATOMIC_CONTEXT_AND_DISABLED_PASS',post_pins_match=True,
            direct_cases_per_image=84,context_lifecycle_cases_per_image=14,default_off_exact=True,
            original_and_candidate_read_work_equal=True,measured_suites=list(pairs),
            limits=['Synthetic AXI and MMU/PMA response fixture, not CVA6 MMU/PMP or SoC acceptance',
                    'Command time excludes SDK preparation, complete GGML and model execution',
                    'Separate nonzero seed/continuation and M4 AKV/RVV handoff remain required'])
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
    return 0 if result['state']=='BALANCED_COMPLETE_CONTROLLER_ATOMIC_CONTEXT_AND_DISABLED_PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();sys.exit(run(args.output,args.execute_reviewed))
