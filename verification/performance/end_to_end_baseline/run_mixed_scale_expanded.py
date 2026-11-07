#!/usr/bin/env python3
"""Reuse the verified normal core/reference sources; test exact exponent recoding."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from audit import digest, require, verify_pins
from prepare_wide_soc import ROOT, HERE, RUNS
from run_supply_sdk import bind

PARENT = RUNS/'e2e_mixed_scale_component_20261106_02'
WRAPPER = ROOT/'hardware/src/vlsu/qbs/experimental/qbs_fp16_f32_scale.sv'


def sources(c, tb):
    edits = []
    def replace(text, old, new):
        require(text.count(old)==1,'Exact expanded-case anchor required')
        edits.append(dict(before=old,after=new)); return text.replace(old,new,1)
    c=replace(c,'ew>=113 && ew<=142','ew>=103 && ew<=142')
    c=replace(c,'(113u+(w%30))','(103u+(w%40))')
    c=replace(c,'    for(unsigned i=0;i<100000;++i) {',
        '''    for(unsigned fraction=1;fraction<1024;++fraction)
        for(unsigned sign=0;sign<2;++sign)
            emit(0x3f800000u,as_bits((float)fraction*0x1p-24f)|(sign<<31));
    for(unsigned i=0;i<100000;++i) {''')
    tb=replace(tb,'  qbs_mixed_scale #(.TagWidth(20)) dut (','  qbs_fp16_f32_scale #(.TagWidth(20)) dut (')
    tb=replace(tb,'cases==110025','cases==112071')
    return c,tb,edits


def run(output):
    out=output.absolute(); require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh verification output required')
    out.mkdir(parents=True,exist_ok=False); pins={}; commands=[]
    result=dict(state='PREPARING',component_only=True,full_controller_integrated=False,
                production_rtl_changed=False,performance_measured=False,synthesis_run=False)
    def pin(p,s=None):bind(pins,p,s)
    def command(argv,name,bound):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=name,argv=argv,timeout_seconds=bound))
        result['state']=name;(out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
        with (out/(name+'.log')).open('xb') as stream:
            child=subprocess.run(argv,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=bound)
        commands[-1]['returncode']=child.returncode;require(child.returncode==0,name+' failed')
        verify_pins(pins);return (out/(name+'.log')).read_text()
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','COMPILER_PATH','GCC_EXEC_PREFIX','LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
    try:
        pin(Path(__file__));pin(WRAPPER);pin(PARENT/'result.json');parent=json.loads((PARENT/'result.json').read_text())
        require(parent['state']=='MIXED_SCALE_HOST_AND_FPNEW_COMPONENT_PASS' and parent['post_pins_match'],
                'Verified normal core/reference required')
        pin(PARENT/'source-pins.json',parent['source_pins_sha256']);old=json.loads((PARENT/'source-pins.json').read_text())
        for folder in ('src','include'):
            for p in (PARENT/folder).rglob('*'):
                if not p.is_file():continue
                pin(p,old[str(p)]);target=out/folder/p.relative_to(PARENT/folder)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        c=out/'src/mixed_scale_oracle.c';tb=out/'src/qbs_mixed_scale_tb.sv'
        generated_c,generated_tb,edits=sources(c.read_text(),tb.read_text())
        c.write_text(generated_c);tb.write_text(generated_tb)
        wrapper=out/'src'/WRAPPER.name;shutil.copyfile(WRAPPER,wrapper)
        (out/'transforms.json').write_text(json.dumps(edits,indent=2)+'\n')
        for p in out.rglob('*'):
            if p.is_file():pin(p)
        recipes={r['label']:r['argv'] for r in json.loads((PARENT/'commands.json').read_text())}
        def remap(argv):return [str(out)+v[len(str(PARENT)):] if v.startswith(str(PARENT)+'/') else
            v.replace('='+str(PARENT)+'/', '='+str(out)+'/').replace('+incdir+'+str(PARENT)+'/', '+incdir+'+str(out)+'/') for v in argv]
        command(remap(recipes['HOST_BUILD']),'host-build',60);pin(out/'oracle')
        host=command([out/'oracle',out/'vectors.txt'],'host-oracle',60);pin(out/'vectors.txt')
        rows=re.findall(r'^MIXED_SCALE_ORACLE_PASS total=(\d+) admitted=(\d+) rejected=(\d+) exact=(\d+) tie_even=(\d+) tie_odd=(\d+) carry=(\d+)$',host,re.M)
        require(len(rows)==1,'Expanded host oracle did not complete')
        counts=dict(zip(('total','admitted','rejected','exact','tie_even','tie_odd','carry'),map(int,rows[0])))
        require(counts['total']==112071 and min(counts[k] for k in ('exact','tie_even','tie_odd','carry'))>0,'Expanded oracle coverage incomplete')
        compile=remap(recipes['VCS_COMPILE']);compile.insert(compile.index(str(tb)),str(wrapper))
        command(compile,'compile',600);pin(out/'simv')
        for p in Path(str(out/'simv')+'.daidir').rglob('*.so'):pin(p)
        text=command([out/'simv','-no_save','+VECTORS='+str(out/'vectors.txt')],'simulation',300)
        require(not re.search(r'Fatal:|Error:|\bFAIL\b',text),'Simulator failure')
        records=re.findall(r'^MIXED_SCALE_RTL_PASS total=(\d+) admitted=(\d+) rejected=(\d+) checked=(\d+) cancelled=(\d+) bubbles=(\d+) resets=(\d+) clears=(\d+) longest_ii1=(\d+) latency=3 host_bits=1 fpnew_bits=1 flags=1$',text,re.M)
        require(len(records)==1,'Complete unique RTL result required')
        actual=dict(zip(('total','admitted','rejected','checked','cancelled','bubbles','resets','clears','longest_ii1'),map(int,records[0])))
        require(all(actual[k]==counts[k] for k in ('total','admitted','rejected')) and
                actual['checked']+actual['cancelled']==actual['admitted'] and actual['longest_ii1']>=16,
                'Expanded reference/DUT work differs')
        verify_pins(pins);result.update(state='FP16_FP32_EXPANDED_SCALE_COMPONENT_PASS',host=counts,measured=actual,
            original_normal_core_sha256=old[str(PARENT/'src/qbs_mixed_scale.sv')],
            parent_result_sha256=digest(PARENT/'result.json'),post_pins_match=True,
            arithmetic='Same 24x11 significand core; exact reciprocal power-of-two exponent recoding',
            latency=3,initiation_interval=1,half_subnormal_inputs_added=2046,
            limits=['Experimental component only; no QBS scheduler/controller or whole-model speedup acceptance',
                    'Conservative normal-result domain; all other classes require original FPU fallback'])
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result['source_pins_sha256']=digest(out/'source-pins.json')
        result['artifacts']={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('result.json','status.json')}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
