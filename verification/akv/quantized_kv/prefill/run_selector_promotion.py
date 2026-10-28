#!/usr/bin/env python3
"""Standard libraries, graph and two real models after shared selector promotion."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    scripts=['build_ggml_integration.py','build_graph_test.py','run_graph_qemu.py',
             'run_model_qemu.py','run_qwen3_model_qemu.py','run_replay.py']
    pins={str(p):digest(p) for p in [Path(__file__),*(HERE/s for s in scripts)]}
    def save(name,value):
        p=out/name;tmp=p.with_suffix(p.suffix+'.tmp')
        tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
    save('pipeline-pins.json',pins)
    def verify():
        for p,h in pins.items():
            if digest(p)!=h:raise RuntimeError('Pipeline drift: '+p)
    def run(label,script,arguments,expected='PASS'):
        verify();directory=out/label
        argv=[sys.executable,'-B',str(HERE/script),str(directory),*map(str,arguments)]
        save(label+'.command.json',argv)
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=10800)
        verify();result=json.loads((directory/'result.json').read_text())
        if result['state']!=expected:raise RuntimeError('Unexpected stage state: '+label)
        return dict(directory=str(directory),result_sha256=digest(directory/'result.json'))
    result=dict(state='FAIL',performance_measured=False)
    try:
        stages={}
        stages['libraries']=run('libraries','build_ggml_integration.py',[])
        stages['graph-build']=run('graph-build','build_graph_test.py',['--library-build',out/'libraries'],'BUILT_NOT_EXECUTED')
        jobs=[('graph','run_graph_qemu.py',['--graph-build',out/'graph-build']),
              ('qwen25','run_model_qemu.py',['--library-build',out/'libraries']),
              ('qwen3','run_qwen3_model_qemu.py',['--library-build',out/'libraries'])]
        # Read-only consumers of the same sealed libraries; outputs are disjoint.
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={label:pool.submit(run,label,script,args) for label,script,args in jobs}
            for label,future in futures.items():stages[label]=future.result()
        verify();result.update(state='PASS',stages=stages,pipeline_pins_match=True)
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:save('result.json',result)


if __name__=='__main__':main()
