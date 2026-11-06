#!/usr/bin/env python3
"""Build reviewed matrix-dot SoCs using the unchanged native VCS/Make flow."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from audit import digest,require,verify_pins
from run_projection_resources import ROOT,VERIFY,HERE

sys.path.insert(0,str(VERIFY/'verification'))
from ara_verify.vcs_source_manifest import collect
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_tile_context_engine import run_command

BASE=VERIFY/'verification/out/e2e_vcs_build_20261106_01'
BASE_SHA='32190b89a1dcf5ce0bb43a201a7b26ba23830fc753c9639837837d525a79c77c'
CONFIG_COMMIT='39f745675'
FEATURE='+define+ARA_QBS_WIDE_MATRIX_DOT=1'
CORE=tuple('hardware/src/vlsu/qbs/'+name+'.sv' for name in
           ('qbs_compute_engine','qbs_dot_array','qbs_engine','qbs_profile_decoder','qbs_profile_engine_int'))
GLUE=('hardware/Makefile','hardware/src/vlsu/vlsu.sv')


def compiler_tool(name):
    require(name in ('vcs','g++','make','python3'),'Unknown compiler tool')
    path=shutil.which(name) if name=='vcs' else '/usr/bin/'+name
    require(path and Path(path).is_file(),'Missing compiler tool: '+name)
    return path


def expected_graph(text,wide):
    require(wide in (0,1),'Invalid width')
    lines=[s.strip() for s in text.splitlines() if s.strip()]
    require(FEATURE not in lines and '+define+ARA_QBS_VRF_CONTINUATION=1' in lines,'Wrong baseline graph')
    result=[]
    for line in lines:
        result.append(line)
        if wide and line=='+define+ARA_QBS_VRF_CONTINUATION=1':result.append(FEATURE)
    return result


def check_config(path,baseline,wide):
    lines=path.read_text().splitlines();require(all(s.count('=')==1 for s in lines),'Malformed configuration')
    data=dict(s.split('=') for s in lines)
    require(len(data)==len(lines) and data==dict(baseline,qbs_matrix_dot=str(wide)),
            'Wrong or duplicate simulator configuration')
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wide',type=int,choices=(0,1),required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--timeout',type=int,default=7200)
    a=p.parse_args();out=a.output.absolute()
    require(out==out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output required')
    require(1<=a.timeout<=7200,'Invalid compile bound')
    require(digest(BASE/'result.json')==BASE_SHA,'Accepted SoC baseline drift')
    baseline=json.loads((BASE/'result.json').read_text())
    require(baseline['state']=='CANONICAL_SOC_BUILT_NOT_EXECUTED' and baseline['post_pins_match'], 'Invalid baseline')
    for name in ('make.command.json','source-pins.json','sim/vcs_source_manifest.json'):
        path=BASE/name
        expected=baseline['artifact_pins'].get(str(path),baseline['image_pins'].get(str(path)))
        require(expected and digest(path)==expected,'Baseline input record drift: '+name)
    prior_pins=json.loads((BASE/'source-pins.json').read_text())
    gate=ROOT/'verification/performance/evidence/matrix_engine_pair_20261106_01/result.json'
    accepted=json.loads(gate.read_text())
    require(accepted['state']=='MATRIX_FULL_ENGINE_COMPOSITE_REAUDITED','Full engine gate incomplete')
    measured=Path(accepted['run']);require(digest(measured/'result.json')==accepted['result_sha256'] and
        digest(measured/'source-pins.json')==accepted['source_pins_sha256'],'Engine receipt drift')
    engine_pins=json.loads((measured/'source-pins.json').read_text());approved={}
    for rel in CORE:
        sha=engine_pins.get(str(ROOT/rel));require(sha and digest(ROOT/rel)==digest(VERIFY/rel)==sha,'Unreviewed engine: '+rel)
        approved[str(VERIFY/rel)]=sha
    for rel in GLUE:
        blob=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'show',CONFIG_COMMIT+':'+rel])
        sha=hashlib.sha256(blob).hexdigest()
        require(digest(ROOT/rel)==digest(VERIFY/rel)==sha,'Unreviewed configuration glue: '+rel)
        approved[str(VERIFY/rel)]=sha
    original=json.loads((BASE/'sim/vcs_source_manifest.json').read_text())
    require(original['repo_root']==str(VERIFY),'Wrong baseline source root')
    for row in original['files']:
        require(digest(row['path'])==approved.get(row['path'],row['sha256']),
                'Unrelated design/input drift: '+row['path'])
    require([s.strip() for s in (BASE/'expected-sources.f').read_text().splitlines() if s.strip()]==
            [s.strip() for s in Path(original['filelist']).read_text().splitlines() if s.strip()],
            'Baseline expected graph differs from compiled graph')
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,wide=a.wide,
               source_root=str(VERIFY),performance_measured=False,simulations_launched=0)
    pins={};commands=[]
    def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path):
        path=str(Path(path).resolve(strict=True));sha=digest(path)
        require(path not in pins or pins[path]==sha,'Pin conflict');pins[path]=sha
    def started(pid):state['child_pid']=pid;save()
    env=os.environ.copy()
    for key in ('MAKEFLAGS','MFLAGS','MAKEFILES','GNUMAKEFLAGS','GCC_EXEC_PREFIX','COMPILER_PATH',
                'LIBRARY_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LD_PRELOAD'):env.pop(key,None)
    env.update(PYTHONPATH=str(VERIFY/'verification'),PYTHONDONTWRITEBYTECODE='1',CCACHE_DISABLE='1')
    env['PATH']='/usr/bin:'+str(Path(compiler_tool('vcs')).parent)+':/bin'
    def run(argv,label,bound=120):
        argv=list(map(str,argv));resolved=shutil.which(argv[0]);require(resolved,'Missing tool');argv[0]=resolved;pin(resolved)
        verify_pins(pins);state['state']=label.upper();save()
        commands.append(dict(label=label,argv=argv,timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        try:require(run_command(argv,out/(label+'.log'),bound,env,started)==0,label+' failed')
        finally:state['child_pid']=None;save()
        return (out/(label+'.log')).read_text()
    try:
        for path in (Path(__file__),HERE/'audit.py',HERE/'run_projection_resources.py',
                     ROOT/'verification/qbs/run_tile_context_engine.py',ROOT/'verification/qbs/run_half_scale_soc.py',
                     gate,measured/'result.json',measured/'source-pins.json',BASE/'result.json',BASE/'make.command.json',
                     BASE/'expected-sources.f',BASE/'sim/vcs_source_manifest.json',VERIFY/'hardware/bender',
                     VERIFY/'verification/ara_verify/vcs_source_manifest.py'):
            pin(path)
        pins.update(approved)
        for row in original['files']:pin(row['path'])
        command=list(json.loads((BASE/'make.command.json').read_text())['argv'])
        for i,word in enumerate(command):
            if word.startswith('buildpath='):command[i]='buildpath='+str(out/'hardware-build')
            elif word.startswith('sim_dir='):command[i]='sim_dir='+str(out/'sim')
        command.append('qbs_matrix_dot='+str(a.wide))
        dry=run([command[0],'-n',*command[1:]],'dry-run')
        render=[shlex.split(line) for line in dry.splitlines() if 'script verilator --no-default-target' in line]
        require(len(render)==1 and render[0][-2]=='>','Unexpected Bender recipe')
        graph_text=run(render[0][:-2],'render-graph')
        expected=expected_graph((BASE/'expected-sources.f').read_text(),a.wide)
        require([s.strip() for s in graph_text.splitlines() if s.strip()]==expected,'Source graph/order/defines differ')
        planned=out/'planned.f';planned.write_text(graph_text);pin(planned)
        uvm=[Path(s) for s in next(w for w in command if w.startswith('verify_extra_sources=')).split('=',1)[1].split()]
        inventory=collect(planned,VERIFY,uvm)
        for row in inventory:pin(row['path'])
        # Reuse the existing strict compiler-command/lint checker unchanged.
        spec=importlib.util.spec_from_file_location('matrix_native_compile_contract',
             VERIFY/'verification/akv/canonical_promotion/canonical_soc/build.py')
        base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
        compiler=base.load_common()
        for module in tuple(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(root) for root in (ROOT,VERIFY)):
                if str(Path(path).resolve()) in prior_pins:
                    require(digest(path)==prior_pins[str(Path(path).resolve())],'Inherited checker changed: '+path)
                pin(path)
        for path in (compiler.SOC_COMPILE_PRIOR,compiler.SOC_COMPILE_PRIOR.parent/'vcs_source_manifest.json'):
            pin(path)
        for tool in ('vcs','g++','make','python3'):
            path=compiler_tool(tool)
            old=prior_pins.get(path,prior_pins.get(str(Path(path).resolve())))
            require(old and digest(path)==old,'Compiler tool differs from baseline: '+tool);pin(path)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        (out/'approval.json').write_text(json.dumps(dict(core_gate=str(gate),glue_commit=CONFIG_COMMIT,
             source_hashes=approved,verification_commit=subprocess.check_output(
                 ['/usr/bin/git','-C',str(VERIFY),'rev-parse','HEAD'],text=True).strip()),indent=2)+'\n')
        if not a.execute:
            state['state']='MATRIX_SOC_PREFLIGHT_NOT_COMPILED'
        else:
            run(command,'compile',a.timeout)
            actual=out/'hardware-build/vcs/bender_script_default'
            require(actual.read_text().splitlines()==graph_text.splitlines(),'Rendered graph changed at compile')
            sim=out/'sim';config=check_config(sim/'simulator.conf',baseline['config'],a.wide)
            manifest=json.loads((sim/'vcs_source_manifest.json').read_text());extras=[out/'hardware-build/work-dpi/elfloader.o',*uvm]
            require(manifest['repo_root']==str(VERIFY) and manifest['filelist']==str(actual) and
                    manifest['extra_sources']==list(map(str,extras)) and manifest['files']==collect(actual,VERIFY,extras),
                    'Actual source/header inventory differs')
            for row in manifest['files']:
                require(row['path'] in (str(actual),str(extras[0])) or pins.get(row['path'])==row['sha256'],
                        'Compile input not approved before execution')
            lint=compiler.check_soc_compile((sim/'comp.vcs.log').read_text(),0,base.expected_vcs(out,Path(compiler_tool('vcs'))),VERIFY)
            image=compiler.s.hashes(compiler.s.image_files(sim/'simv'))
            verify_pins(pins)
            state.update(state='MATRIX_SOC_BUILT_NOT_EXECUTED',simv=str(sim/'simv'),config=config,
                         image_pins=image,lint=lint,post_pins_match=True)
        verify_pins(pins)
        state.update(source_pins_sha256=digest(out/'source-pins.json'),approved_source_hashes=approved,
            artifacts={str(x):digest(x) for x in out.iterdir() if x.is_file() and x.name not in ('status.json','result.json')})
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
