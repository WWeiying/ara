#!/usr/bin/env python3
"""Paired full QBS/shared-reader tests; no global compile or FPGA job."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

from audit import digest,require,verify_pins
from matrix_dot_pair import candidate_vectors
from matrix_engine_pair import adapt_wrapper,adapt_bench,pair
from run_projection_resources import ROOT,VERIFY,HERE

sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--component-run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();prior=a.component_run.resolve(strict=True)
    require(out.is_relative_to(VERIFY/'verification/out'),'Use sole verification output area')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[];state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,
        default_enabled=False,full_soc_tested=False,model_performance_measured=False,area_measured=False)
    def save(): (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path):
        path=str(Path(path).resolve(strict=True));sha=digest(path)
        require(path not in pins or pins[path]==sha,'Input drift: '+path);pins[path]=sha
    def started(pid):state['child_pid']=pid;save()
    def run(argv,label,bound=120):
        argv=list(map(str,argv));resolved=shutil.which(argv[0]);require(resolved,'Missing tool');argv[0]=resolved;pin(resolved)
        verify_pins(pins);commands.append(dict(label=label,argv=argv,timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        state['state']=label.upper();save()
        try:require(run_command(argv,out/(label+'.log'),bound,os.environ.copy(),started)==0,label+' failed')
        finally:state['child_pid']=None;save()
        return (out/(label+'.log')).read_text()
    try:
        old=json.loads((prior/'result.json').read_text())
        require(old['state']=='MATRIX_DOT_COMPONENT_PAIR_PASS','Component gate incomplete')
        directory=ROOT/'verification/qbs'
        for path in (Path(__file__),HERE/'matrix_engine_pair.py',HERE/'matrix_dot_pair.py',HERE/'audit.py',
                     HERE/'projection_resources.py',HERE/'run_projection_resources.py',prior/'result.json',
                     directory/'Makefile',directory/'run_tile_context_engine.py',directory/'run_half_scale_soc.py'):
            pin(path)
        generator_source=ROOT/'verification/akv/canonical_promotion/generate_standalone.py'
        spec=importlib.util.spec_from_file_location('matrix_standalone',generator_source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        generated=module.generate(ROOT,'qbs',directory/'qbs_engine_tb.sv',out/'original')
        for name,sha in {**generated['input_pins'],**generated['artifact_pins']}.items():
            require(digest(name)==sha,'Composition drift');pin(name)
        pin(out/'original/generation.json')
        wrapper=out/'matrix_wrapper.sv';bench=out/'matrix_suite.sv'
        wrapper.write_text(adapt_wrapper((out/'original/composed_engine.sv').read_text()))
        bench.write_text(adapt_bench((out/'original/original_suite.sv').read_text()))
        pin(wrapper);pin(bench)
        for root in ('hardware/include','hardware/deps/common_cells/include','hardware/deps/axi/include'):
            for path in (ROOT/root).rglob('*.svh'):pin(path)
        sources=run(['make','-s','--no-print-directory','-C',directory,
                     "--eval=matrix-engine-sources:;@printf '%s\\n' $(RTL_SOURCES)",'matrix-engine-sources'],'sources').splitlines()
        require(sources and all(Path(x).is_file() for x in sources),'RTL inventory')
        for path in sources:pin(path)
        vectors=[]
        for name in ('matrix','real-m1','real-m4'):
            source=prior/(name+'-base.txt');require(old['artifacts'].get(str(source))==digest(source),'Vector identity')
            pin(source);b=out/(name+'-base.txt');c=out/(name+'-wide.txt')
            b.write_bytes(source.read_bytes());c.write_text(candidate_vectors(b.read_text()));pin(b);pin(c)
            vectors.append((name,b,c,1 if name=='matrix' else 0,name!='matrix'))
        cc=[shutil.which('gcc'),'-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-frounding-math']
        require(cc[0],'GCC missing');inputs=[directory/'qbs_command_vectors.c',directory/'qbs_ref.c']
        for i,source in enumerate(inputs):
            deps=run([*cc,'-M','-MT','object',source],f'deps-{i}')
            for dep in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(out/dep if not Path(dep).is_absolute() else dep)
        generator=out/'generator';run([*cc,*inputs,'-lm','-o',generator],'generator-compile');pin(generator)
        b=out/'contexts-base.txt';c=out/'contexts-wide.txt'
        run([generator,b,'--context-suite'],'context-generate');pin(b)
        c.write_text(candidate_vectors(b.read_text()));pin(c);vectors.append(('contexts',b,c,12,False))
        includes=['+incdir+'+str(ROOT/'hardware/include'),'+incdir+'+str(ROOT/'hardware/deps/common_cells/include'),
                  '+incdir+'+str(ROOT/'hardware/deps/axi/include')]
        images=[]
        for mode in (0,1):
            build=out/f'build-{mode}';build.mkdir()
            run(['vcs','-full64','-sverilog','-timescale=1ns/1ps','+lint=TFIPC-L',*includes,*sources,wrapper,bench,
                 '-top','qbs_engine_tb',f'-pvalue+qbs_engine_tb.Wide={mode}',
                 '-Mdir='+str(build/'csrc'),'-o',build/'simv'],f'compile-{mode}',600)
            pin(build/'simv');libs=list((build/'simv.daidir').rglob('*.so'));require(libs,'Missing VCS libraries')
            for path in libs:pin(path)
            images.append(build/'simv')
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        results=[]
        for name,b,c,contexts,functional in vectors:
            for gap in (0,3):
                extra=['+QBS_FUNCTIONAL_ONLY'] if functional else []
                if name=='contexts':extra.append('+QBS_CONTEXT_SUITE')
                logs=[run([image,'+QBS_COMMAND_VECTOR_FILE='+str(vector),f'+QBS_RESPONSE_GAP={gap}',*extra],
                          f'run-{name}-gap{gap}-{mode}',600) for mode,(image,vector) in enumerate(zip(images,(b,c)))]
                measured=pair(*logs,b.read_text(),c.read_text(),gap,contexts,functional)
                results.append(dict(vector=name,measured=measured))
        verify_pins(pins)
        state.update(state='MATRIX_DOT_FULL_ENGINE_PAIR_PASS',results=results,
                     source_pins_sha256=digest(out/'source-pins.json'),
                     artifacts={str(x):digest(x) for x in out.iterdir() if x.is_file() and x.name not in ('status.json','result.json')},
                     limitations=['Complete QBS command/shared-reader/commit, not CVA6 or SDK preparation',
                                  'Functional generic SRAM model, not mapped area/timing evidence',
                                  'Default stays off pending native full-call and representative RVV regression'])
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
