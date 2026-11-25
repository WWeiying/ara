#!/usr/bin/env python3
"""Successor: freeze the Python protocol checker with each RTL precheck queue."""
import argparse
import concurrent.futures
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
REV = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
ALLOWED = ('DC_MATCHED_RTL_BUILT_NOT_EXECUTED',
           'RECONSTRUCTED_BASELINE_RTL_BUILT_NOT_EXECUTED')


def helper():
    spec = importlib.util.spec_from_file_location('power_precheck_primitives', HERE/'precheck.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def prepare(output, image, manifest, parallel):
    m = helper()
    m.prepare(output,image,manifest,parallel)
    archive = subprocess.check_output(['git','-C',str(ROOT),'archive',REV,'verification/ara_verify'])
    (output/'inputs/checker.tar').write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if not (member.isfile() or member.isdir()) or Path(member.name).is_absolute() or '..' in Path(member.name).parts:
                raise ValueError('Unsafe checker archive')
        tar.extractall(output/'inputs/checker')
    shutil.copyfile(__file__,output/'inputs/precheck_v2.py')
    plan = json.loads((output/'plan.json').read_text())
    plan.update(protocol_checker_commit=REV,
                protocol_pythonpath=str(output/'inputs/checker/verification'),
                accepted_image_states=list(ALLOWED))
    m.save(output/'plan.json',plan)
    pins = json.loads((output/'source-pins.json').read_text())
    for p in (output/'inputs').rglob('*'):
        if p.is_file():
            pins[str(p)] = m.sha(p)
    pins[str(output/'plan.json')] = m.sha(output/'plan.json')
    m.save(output/'source-pins.json',pins)
    m.verify(pins)


def execute(output):
    m = helper()
    if Path(__file__).resolve() != output/'inputs/precheck_v2.py' or (output/'attempt.json').exists():
        raise ValueError('Frozen one-shot successor required')
    m.save(output/'attempt.json',dict(pid=os.getpid(),started=time.time()))
    plan = json.loads((output/'plan.json').read_text())
    pins = json.loads((output/'source-pins.json').read_text())
    m.verify(pins)
    image = Path(plan['image'])
    build = json.loads((image/'build.json').read_text())
    if build['state'] not in ALLOWED:
        raise ValueError('No admitted RTL build receipt')
    image_pins = build['image_pins']
    m.verify(image_pins)
    m.verify(json.loads((image/'source-pins.json').read_text()))
    simv = image/'sim/simv'
    image_plan = json.loads((image/'plan.json').read_text())
    env = dict(image_plan['environment'],PYTHONPATH=plan['protocol_pythonpath'],
               PYTHONDONTWRITEBYTECODE='1')
    stop, lock, completed = threading.Event(),threading.Lock(),[]

    def one(c):
        if stop.is_set():
            return dict(id=c['id'],state='NOT_DISPATCHED_AFTER_FAILURE')
        work=output/'runs'/c['id']
        work.mkdir()
        result=dict(id=c['id'],state='FAIL',scope=plan['scope'],
                    image_state=build['state'],elf_sha256=c['elf_sha256'])
        start=time.monotonic()
        try:
            m.verify({c['elf']:c['elf_sha256'],str(simv):image_pins[str(simv)]})
            m.run_command([simv,'-no_save','-l',work/'run.vcs.log',
                '+PRELOAD='+c['elf'],'+TESTCASE='+c['id'],'+NO_FSDB','+NO_INSTR_TRACE',
                '+VECTOR_TRACE='+str(work/'vector.csv'),'+COMMIT_TRACE='+str(work/'commit.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000',
                *c.get('plusargs',[])],work,'VCS',env,c['timeout_seconds'])
            text=(work/'run.vcs.log').read_text()
            if 'Core Test *** SUCCESS ***' not in text or m.re.search(
                    r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed|\bFAILED\b',text):
                raise ValueError('RTL completion/error gate')
            subst=dict(run=str(work),log=str(work/'run.vcs.log'),result=str(work/'numerical.json'))
            m.run_command([s.format(**subst) for s in c['checker']],work,'NUMERICAL',env,600)
            numeric=json.loads((work/'numerical.json').read_text())
            if numeric['state']!='PASS':
                raise ValueError('Numerical gate')
            m.run_command([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write',
                '--vector-trace',work/'vector.csv','--log',work/'run.vcs.log',
                '--simv',simv,'--elf',c['elf'],'--output',work/'protocol.json'],
                work,'PROTOCOL',env,1200)
            proof=json.loads((work/'protocol.json').read_text())
            if proof['status']!='PASS' or proof['issues'] or any(proof['contract_counts'][k]
                    for k in ('exceptions','protocol_errors','outstanding')):
                raise ValueError('Independent protocol/completion gate')
            for field,want in (('elf_sha256',c['elf_sha256']),('simv_sha256',image_pins[str(simv)]),
                               ('log_sha256',m.sha(work/'run.vcs.log')),
                               ('vector_trace_sha256',m.sha(work/'vector.csv'))):
                if proof[field]!=want:
                    raise ValueError('Protocol identity '+field)
            result.update(state='PASS',numeric=numeric,independent_protocol_checked=True)
        except Exception as exc:
            result.update(state='TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL',error=repr(exc))
            stop.set()
        result['wall_seconds']=time.monotonic()-start
        m.save(work/'result.json',result)
        m.save(work/'status.json',dict(state=result['state']))
        with lock:
            completed.append(dict(id=c['id'],state=result['state']))
            m.save(output/'status.json',dict(state='STOPPING_AFTER_FAILURE' if stop.is_set() else 'RUNNING',
                   total=len(plan['cases']),completed=len(completed),cases=completed))
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=plan['parallel']) as pool:
        results=list(pool.map(one,plan['cases']))
    drift=None
    try:
        m.verify(pins)
        m.verify(image_pins)
        m.verify(json.loads((image/'source-pins.json').read_text()))
    except Exception as exc:
        drift=repr(exc)
    state='PASS' if not drift and all(r['state']=='PASS' for r in results) else 'INCOMPLETE'
    m.save(output/'result.json',dict(state=state,cases=results,pin_error=drift,image=str(image),
                                    rtl_precheck_only=True,image_state=build['state'],scope=plan['scope']))
    m.save(output/'status.json',dict(state=state,total=len(results),completed=len(completed),cases=completed))
    return int(state!='PASS')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',type=Path)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--parallel',type=int,default=4)
    a=p.parse_args()
    if a.action=='prepare':
        prepare(a.output.resolve(),a.image.resolve(),a.manifest.resolve(),a.parallel)
        return 0
    return execute(a.output.resolve())


if __name__=='__main__':
    raise SystemExit(main())
