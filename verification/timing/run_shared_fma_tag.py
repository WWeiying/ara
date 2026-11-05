#!/usr/bin/env python3
"""Reproduce X-payload tag assertion, then qualify exact four-state comparison."""
import argparse
from pathlib import Path
import shutil
import subprocess
import run_operand_ext as api
from run_shared_fma import SOURCES


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--reproduce',action='store_true')
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    (out/'src').mkdir()
    sources=SOURCES[:-1]+['verification/timing/shared_fma_tag_tb.sv']
    for f in sources: shutil.copy2(api.ROOT/f,out/'src'/Path(f).name)
    shutil.copytree(api.ROOT/'hardware/deps/common_cells/include',out/'include')
    shutil.copy2(__file__,out/'worker.py')
    api.save(out/'source-pins.json',{str(f):api.sha(f) for f in out.rglob('*') if f.is_file()})
    cmd=['vcs','-full64','-sverilog','-timescale=1ns/1ps','-top','shared_fma_tag_tb',
         '-o','simv','+incdir+include',*['src/'+Path(f).name for f in sources]]
    api.command(cmd,out,out/'compile.log',None)
    runs=[]
    for corrupt in ([False] if a.reproduce else [False,True]):
        log=out/('corrupt.log' if corrupt else 'run.log')
        with log.open('w') as stream:
            rc=subprocess.run(['timeout','30','./simv','-no_save',*(['+CORRUPT'] if corrupt else [])],
                              cwd=out,stdout=stream,stderr=subprocess.STDOUT).returncode
        text=log.read_text()
        if rc==124: raise ValueError('Tag test timeout')
        if 'logical_equal=x case_equal=1 aux_equal=1' not in text: raise ValueError('Hypothesis not reproduced')
        failure='Shared FMA sublane metadata divergence' in text
        if failure != (a.reproduce or corrupt): raise ValueError('Unexpected checker behavior: '+str(log))
        if not failure and ('SHARED_FMA_TAG_PASS' not in text or 'Fatal:' in text or rc):
            raise ValueError('Positive check did not pass')
        runs.append({'corrupt':corrupt,'returncode':rc,'expected_rejection':failure})
    api.verify(out)
    api.save(out/'report.json',{'state':'REPRODUCED' if a.reproduce else 'PASS','runs':runs})
    print(api.read(out/'report.json'))


if __name__=='__main__': main()
