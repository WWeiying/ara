#!/usr/bin/env python3
"""Run unchanged engine suite assertions through a test-only reader composition."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

from compose_standalone import ROOT, HERE, compose, adapt_tb
from prepare_storage import validate_snapshot
from prepare import digest


def verify(pins):
    for name, sha in pins.items():
        if digest(name) != sha:
            raise ValueError('Input changed: '+name)


def check_log(text, kind, code, cases=36):
    marker = (f'QBS engine PASS: {cases} functional cases plus four fault classes' if kind == 'qbs' else
        'AKV engine PASS: v1 D64/D128 plus v2 D64/D96/D128 and segmented D256 row/column views, tails, counters, validation, and faults')
    if code or text.splitlines().count(marker) != 1 or re.search(r'Fatal:|Error(?:-|:)|TIMEOUT',text):
        raise ValueError('Original engine suite did not complete cleanly')
    return marker


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--kind',choices=('qbs','akv'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    snapshot=args.snapshot.resolve(strict=True)
    report=validate_snapshot(snapshot)
    original=ROOT/f'hardware/src/vlsu/{args.kind}/{args.kind}_engine.sv'
    bench=ROOT/f'verification/{args.kind}/{args.kind}_engine_tb.sv'
    vectors=ROOT/'verification/qbs/qbs_command_vectors.txt'
    filelist=Path(report['compile_filelist'])
    vcs=shutil.which('vcs')
    if not vcs:
        raise RuntimeError('Host VCS unavailable')
    own=[Path(__file__).resolve(),HERE/'compose_standalone.py',HERE/'test_compose_standalone.py',
         HERE/'test_run_standalone.py',original,bench,Path(vcs),Path(vcs).resolve()]
    cases=0
    if args.kind=='qbs':
        header=vectors.read_text().splitlines()[0].split()
        if len(header)!=2 or header[0]!='QBSCMD1' or int(header[1])!=36:
            raise ValueError('Expected the complete original36-case vector collection')
        cases=int(header[1]); own.append(vectors)
    pins={**report['input_pins'],**report['artifact_pins'],
          **{str(p):digest(p) for p in own},str(snapshot/'manifest.json'):digest(snapshot/'manifest.json')}
    verify(pins)
    out=args.output.resolve()
    if out.is_relative_to(snapshot):
        raise ValueError('Independent output required')
    out.mkdir(parents=True,exist_ok=False)
    wrapper=out/'composed_engine.sv'
    adapted=out/'original_suite.sv'
    wrapper.write_text(compose(original.read_text(),args.kind))
    adapted.write_text(adapt_tb(bench.read_text(),args.kind))
    pins.update({str(p):digest(p) for p in (wrapper,adapted)})
    def save(name,value):
        tmp=out/(name+'.tmp')
        tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
        tmp.replace(out/(name+'.json'))
    save('source-pins',pins)
    state=dict(state='BUILDING',pid=os.getpid(),child_pid=None,kind=args.kind,
               snapshot=str(snapshot),input_cases=cases,production_promoted=False)
    def execute(command,name,timeout):
        save(name+'.command',list(map(str,command)))
        with (out/(name+'.log')).open('w') as log:
            child=subprocess.Popen(command,cwd=out,stdout=log,stderr=log,start_new_session=True)
            state['child_pid']=child.pid; save('status',state)
            try:
                code=child.wait(timeout=timeout)
                save(name+'.exit',{'exit_code':code})
                return code
            finally:
                try: os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait(); state['child_pid']=None; save('status',state)
    def interrupted(sig,_frame):
        raise InterruptedError(f'Signal {sig}')
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    save('status',state)
    try:
        command=[vcs,'-full64','-sverilog','-timescale=1ns/1ps','-debug_access+all',
                 '+lint=TFIPC-L','-f',str(filelist),str(wrapper),str(adapted),
                 '-top',args.kind+'_engine_tb','-o',str(out/'simv')]
        if execute(command,'compile',600):
            raise RuntimeError('Standalone suite compilation failed')
        if re.search(r'Error-\[|Error:|Fatal:',(out/'compile.log').read_text()):
            raise RuntimeError('Compiler emitted errors')
        verify(pins)
        state['state']='RUNNING'; save('status',state)
        command=[str(out/'simv'),'-no_save']
        if args.kind=='qbs': command+=['+QBS_COMMAND_VECTOR_FILE='+str(vectors)]
        code=execute(command,'suite',600)
        marker=check_log((out/'suite.log').read_text(),args.kind,code,cases)
        verify(pins)
        save('result',dict(state='PASS',kind=args.kind,marker=marker,input_cases=cases,
            original_assertions_and_expected_data_preserved=True,post_pins_match=True,
            snapshot_sha256=digest(snapshot/'manifest.json'),source_pins_sha256=digest(out/'source-pins.json'),
            production_promoted=False,evidence={str(p):digest(p) for p in
                (wrapper,adapted,out/'source-pins.json',out/'compile.log',out/'suite.log',out/'simv',
                 out/'compile.command.json',out/'compile.exit.json',out/'suite.command.json',out/'suite.exit.json')}))
        state['state']='PASS'
    except BaseException as exc:
        state.update(state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL',error=repr(exc))
        save('result',state)
        raise
    finally:
        save('status',state)


if __name__=='__main__':
    main()
