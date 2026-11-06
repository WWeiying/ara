#!/usr/bin/env python3
"""Preserve failed campaign; prove timing cause and complete failed context scope."""
import argparse
import json
import os
from pathlib import Path
import shutil

from audit import digest,require,verify_pins
from matrix_engine_pair import check_mode,pair
from matrix_fault_schedule import prefix,probe_bench,late_fault_proof
from run_projection_resources import ROOT,VERIFY,HERE

import sys
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--failed-run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();old=a.failed_run.resolve(strict=True);out=a.output.resolve()
    require(out.is_relative_to(VERIFY/'verification/out'),'Verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[];state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,
        hardware_changed=False,original_failed_run_preserved=True,model_performance_measured=False)
    def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path):
        path=str(Path(path).resolve(strict=True));sha=digest(path)
        require(path not in pins or pins[path]==sha,'Pin drift');pins[path]=sha
    def started(pid):state['child_pid']=pid;save()
    def run(argv,label,bound=600,expected_failure=False):
        argv=list(map(str,argv));path=shutil.which(argv[0]);require(path,'Tool missing');argv[0]=path;pin(path)
        verify_pins(pins);commands.append(dict(label=label,argv=argv,timeout=bound,expected_failure=expected_failure))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');state['state']=label.upper();save()
        try:
            code=run_command(argv,out/(label+'.log'),bound,os.environ.copy(),started)
            require(code==0 or expected_failure and code==1,'Process failed: '+label)
        finally:state['child_pid']=None;save()
        return (out/(label+'.log')).read_text()
    try:
        old_result=json.loads((old/'result.json').read_text());require(old_result['state']=='FAIL','Expected preserved failure')
        pins.update(json.loads((old/'source-pins.json').read_text()));verify_pins(pins)
        for path in (Path(__file__),HERE/'matrix_fault_schedule.py',HERE/'matrix_replay_probe.svh',HERE/'matrix_engine_pair.py',
                     old/'result.json',old/'commands.json',old/'source-pins.json'):pin(path)
        old_commands=json.loads((old/'commands.json').read_text())
        bench=out/'matrix_fault_suite.sv';bench.write_text(probe_bench((old/'matrix_suite.sv').read_text()));pin(bench)
        small=out/'prefix.txt';small.write_text(prefix((old/'contexts-base.txt').read_text()));pin(small)
        results=[]
        # Re-audit completed scopes of the failed worker without relabeling it.
        for name in ('matrix','real-m1','real-m4','contexts'):
            for gap in (0,3):
                if name=='contexts' and gap==3:continue
                logs=[]
                for mode in (0,1):
                    path=old/f'run-{name}-gap{gap}-{mode}.log';pin(path);logs.append(path.read_text())
                b=old/(name+'-base.txt');c=old/(name+'-wide.txt')
                measured=pair(*logs,b.read_text(),c.read_text(),gap,12 if name=='contexts' else 1 if name=='matrix' else 0,name.startswith('real-'))
                results.append(dict(vector=name,source=str(old),measured=measured))
        images=[]
        for mode in (0,1):
            argv=list(next(r['argv'] for r in old_commands if r['label']==f'compile-{mode}'))
            build=out/f'build-{mode}';build.mkdir()
            argv[argv.index(str(old/'matrix_suite.sv'))]=str(bench)
            argv[argv.index('-o')+1]=str(build/'simv')
            argv=['-Mdir='+str(build/'csrc') if word.startswith('-Mdir=') else word for word in argv]
            argv.insert(1,'+incdir+'+str(HERE));run(argv,f'compile-{mode}')
            pin(build/'simv');libs=list((build/'simv.daidir').rglob('*.so'));require(libs,'Missing VCS libraries')
            for path in libs:pin(path)
            images.append(build/'simv')
            if mode==0:
                passive=run([images[0],'+QBS_COMMAND_VECTOR_FILE='+str(small),'+QBS_CONTEXT_SUITE',
                             '+QBS_RESPONSE_GAP=3'],'passive-prefix',expected_failure=True)
                proof=late_fault_proof(passive)
                (out/'rootcause.json').write_text(json.dumps(proof,indent=2)+'\n')
                fixed=run([images[0],'+QBS_COMMAND_VECTOR_FILE='+str(small),'+QBS_CONTEXT_SUITE',
                           '+QBS_RESPONSE_GAP=3','+MATRIX_FAST_FAULT_DRAIN'],'fast-prefix')
                check_mode(fixed,small.read_text(),0,3,2,False)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        logs=[run([image,'+QBS_COMMAND_VECTOR_FILE='+str(old/('contexts-'+suffix+'.txt')),
                   '+QBS_CONTEXT_SUITE','+QBS_RESPONSE_GAP=3','+MATRIX_FAST_FAULT_DRAIN'],f'contexts-{mode}')
              for mode,(image,suffix) in enumerate(zip(images,('base','wide')))]
        require(all(text.splitlines().count('MATRIX_FAULT_SCHEDULE fast=1')==1 for text in logs),'Wrong error schedule')
        measured=pair(*logs,(old/'contexts-base.txt').read_text(),(old/'contexts-wide.txt').read_text(),3,12,False)
        results.append(dict(vector='contexts',source=str(out),measured=measured))
        verify_pins(pins)
        state.update(state='FULL_ENGINE_PAIR_WITH_FAULT_SCHEDULE_PASS',rootcause=proof,results=results,
                     source_pins_sha256=digest(out/'source-pins.json'),
                     artifacts={str(x):digest(x) for x in out.iterdir() if x.is_file() and x.name not in ('status.json','result.json')},
                     limitations=['Only injected REUSE/RELEASE AXI fault draining uses fast responses',
                                  'All numerical, saved-context and required active-overlap assertions retained',
                                  'Not full SoC, SDK, FPGA, mapped timing or area evidence'])
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
