#!/usr/bin/env python3
"""Build default/wide compute RTL from one source inventory and run matched vectors."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from audit import digest,require,verify_pins
from matrix_dot_pair import candidate_vectors,pair
from run_projection_resources import bench_source,ROOT,VERIFY,HERE

sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--resource-run',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve(); prior=a.resource_run.resolve(strict=True)
    require(out.is_relative_to(VERIFY/'verification/out'),'Use sole verification output area')
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,default_enabled=False,
               full_soc_tested=False,model_performance_measured=False,area_measured=False)
    pins={};commands=[]
    def save(): (out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
    def pin(path):
        path=str(Path(path).resolve(strict=True));sha=digest(path)
        require(path not in pins or pins[path]==sha,'Input drift: '+path);pins[path]=sha
    def started(pid): state['child_pid']=pid;save()
    def run(argv,label,bound=120):
        argv=list(map(str,argv));resolved=shutil.which(argv[0]);require(resolved,'Missing tool');argv[0]=resolved;pin(resolved)
        verify_pins(pins);state['state']=label.upper();save()
        commands.append(dict(label=label,argv=argv,timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        try: require(run_command(argv,out/(label+'.log'),bound,os.environ.copy(),started)==0,label+' failed')
        finally: state['child_pid']=None;save()
        return (out/(label+'.log')).read_text()
    try:
        old=json.loads((prior/'result.json').read_text());require(old['state']=='RTL_PORT_AUDIT_PASS','Unaccepted source vectors')
        # Only vector payloads are inherited. RTL is deliberately the current
        # candidate, not a relabeling of the prior build's source identity.
        for path in (Path(__file__),HERE/'matrix_dot_pair.py',HERE/'audit.py',HERE/'projection_resources.py',
                     HERE/'run_projection_resources.py',HERE/'projection_resource_monitor.svh',prior/'result.json',
                     ROOT/'verification/qbs/Makefile',ROOT/'verification/qbs/qbs_compute_engine_tb.sv',
                     ROOT/'verification/qbs/run_tile_context_engine.py',ROOT/'verification/qbs/run_half_scale_soc.py'): pin(path)
        for root in ('hardware/deps/common_cells/include','hardware/deps/axi/include'):
            for path in (ROOT/root).rglob('*.svh'): pin(path)
        sources=run(['make','-s','--no-print-directory','-C',ROOT/'verification/qbs',
                     "--eval=matrix-pair-sources:;@printf '%s\\n' $(RTL_SOURCES)",'matrix-pair-sources'],'sources').splitlines()
        require(sources and all(Path(x).is_file() for x in sources),'RTL inventory')
        for path in sources: pin(path)
        bench=bench_source((ROOT/'verification/qbs/qbs_compute_engine_tb.sv').read_text())
        anchor='module projection_resource_tb;'; require(bench.count(anchor)==1,'Top anchor')
        bench=bench.replace(anchor,"module projection_resource_tb #(parameter bit Wide = 1'b0);")
        anchor='  qbs_compute_engine dut (';require(bench.count(anchor)==1,'DUT anchor')
        bench=bench.replace(anchor,'  qbs_compute_engine #(.WideMatrixDot(Wide)) dut (')
        source=out/'projection_resource_tb.sv';source.write_text(bench);pin(source)
        vectors=[]
        for name in ('matrix','real-m1','real-m4'):
            original=prior/(name+'.txt'); require(old['artifacts'].get(str(original))==digest(original),'Vector identity')
            pin(original);base=out/(name+'-base.txt');wide=out/(name+'-wide.txt')
            base.write_bytes(original.read_bytes());wide.write_text(candidate_vectors(base.read_text()))
            pin(base);pin(wide);vectors.append((name,base,wide))
        includes=['+incdir+'+str(ROOT/'hardware/include'),'+incdir+'+str(ROOT/'hardware/deps/common_cells/include'),
                  '+incdir+'+str(ROOT/'hardware/deps/axi/include'),'+incdir+'+str(HERE)]
        images=[]
        for wide in (0,1):
            build=out/f'build-{wide}';build.mkdir()
            run(['vcs','-full64','-sverilog','-timescale=1ns/1ps','+lint=TFIPC-L',*includes,*sources,source,
                 '-top','projection_resource_tb',f'-pvalue+projection_resource_tb.Wide={wide}',
                 '-Mdir='+str(build/'csrc'),'-o',build/'simv'],f'compile-{wide}',600)
            pin(build/'simv');libs=list((build/'simv.daidir').rglob('*.so'));require(libs,'Missing VCS libraries')
            for path in libs: pin(path)
            images.append(build/'simv')
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        results=[]
        for name,base,wide in vectors:
            logs=[run([images[mode],'+QBS_COMMAND_VECTOR_FILE='+str(v)],f'run-{name}-{mode}',300)
                  for mode,v in enumerate((base,wide))]
            results.append(dict(vector=name,cases=pair(*logs,base.read_text(),wide.read_text())))
        verify_pins(pins)
        state.update(state='MATRIX_DOT_COMPONENT_PAIR_PASS',results=results,
                     source_pins_sha256=digest(out/'source-pins.json'),
                     artifacts={str(x):digest(x) for x in out.iterdir() if x.is_file() and x.name not in ('status.json','result.json')},
                     limitations=['Compute-level functional/per-port test; not complete SDK or model latency',
                                  'Input delivery is testbench driven; ratios are not native-call speedups',
                                  'Default remains off pending full-engine, SoC and runtime evidence'])
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:save();(out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__':main()
