#!/usr/bin/env python3
"""Pinned, finite RTL prechecks. This worker never launches gate simulation."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)


def verify(pins):
    for name, digest in pins.items():
        if sha(name) != digest:
            raise ValueError('Input drift: ' + name)


def run_command(argv, work, label, env, timeout):
    argv = list(map(str, argv))
    with (work / (label + '.log')).open('x') as stream:
        proc = subprocess.Popen(argv, cwd=work, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)
        save(work / 'status.json', dict(state=label, pid=proc.pid, command=argv))
        try:
            rc = proc.wait(timeout=timeout)
        except BaseException:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise
    if rc:
        raise ValueError(f'{label} exit {rc}')


def prepare(output, image, manifest, parallel):
    if output.exists() or output.parent != OUT or not output.name.startswith('power_precheck_20261117_'):
        raise ValueError('Fresh owned output required')
    if not 1 <= parallel <= 4:
        raise ValueError('Parallel must be 1..4')
    data = json.loads(manifest.read_text())
    cases = data['cases']
    ids = [c['id'] for c in cases]
    if not ids or len(set(ids)) != len(ids) or not all(re.fullmatch(r'[A-Za-z0-9_-]+', x) for x in ids):
        raise ValueError('Invalid cases')
    pins = {str(manifest): sha(manifest), str(image / 'source-pins.json'): sha(image / 'source-pins.json')}
    for c in cases:
        if not c['checker'] or not 1 <= c['timeout_seconds'] <= 10800:
            raise ValueError('Missing checker/budget')
        extra = json.loads(Path(c['source_pins']).read_text())
        for name, digest in extra.items():
            if name in pins and pins[name] != digest:
                raise ValueError('Conflicting input pin: ' + name)
            pins[name] = digest
        pins[c['source_pins']] = sha(c['source_pins'])
        pins[c['elf']] = c['elf_sha256']
        for arg in c['checker']:
            if Path(arg).is_file():
                pins[arg] = sha(arg)
    verify(pins)
    output.mkdir()
    (output / 'inputs').mkdir()
    (output / 'runs').mkdir()
    script = output / 'inputs/precheck.py'
    script.write_bytes(Path(__file__).read_bytes())
    pins[str(script)] = sha(script)
    save(output / 'plan.json', dict(image=str(image), cases=cases, parallel=parallel,
                                   scope=data['scope'], automatic_retry=False))
    pins[str(output / 'plan.json')] = sha(output / 'plan.json')
    save(output / 'source-pins.json', pins)
    save(output / 'status.json', dict(state='PREPARED', total=len(cases), completed=0))


def execute(output):
    if Path(__file__).resolve() != output / 'inputs/precheck.py' or (output / 'attempt.json').exists():
        raise ValueError('Frozen one-shot worker required')
    save(output / 'attempt.json', dict(pid=os.getpid(), started=time.time()))
    plan = json.loads((output / 'plan.json').read_text())
    pins = json.loads((output / 'source-pins.json').read_text())
    verify(pins)
    image = Path(plan['image'])
    build = json.loads((image / 'build.json').read_text())
    if build['state'] != 'DC_MATCHED_RTL_BUILT_NOT_EXECUTED':
        raise ValueError('DC-matched RTL compile has not passed')
    image_pins = build['image_pins']
    verify(image_pins)
    verify(json.loads((image / 'source-pins.json').read_text()))
    simv = image / 'sim/simv'
    image_plan = json.loads((image / 'plan.json').read_text())
    env = dict(image_plan['environment'], PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(image / 'source/verification'))
    stop, lock = threading.Event(), threading.Lock()
    completed = []

    def one(case):
        if stop.is_set():
            return dict(id=case['id'], state='NOT_DISPATCHED_AFTER_FAILURE')
        work = output / 'runs' / case['id']
        work.mkdir()
        result = dict(id=case['id'], state='FAIL', scope='RTL precheck, not power',
                      elf_sha256=case['elf_sha256'], simulator_sha256=image_pins[str(simv)])
        start = time.monotonic()
        try:
            verify({case['elf']: case['elf_sha256'], str(simv): image_pins[str(simv)]})
            run_command([simv, '-no_save', '-l', work / 'run.vcs.log',
                         '+PRELOAD=' + case['elf'], '+TESTCASE=' + case['id'],
                         '+NO_FSDB', '+NO_INSTR_TRACE',
                         '+VECTOR_TRACE=' + str(work / 'vector.csv'),
                         '+COMMIT_TRACE=' + str(work / 'commit.csv'),
                         '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000',
                         *case.get('plusargs', [])], work, 'VCS', env, case['timeout_seconds'])
            text = (work / 'run.vcs.log').read_text()
            if 'Core Test *** SUCCESS ***' not in text or re.search(
                    r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed|\bFAILED\b', text):
                raise ValueError('RTL completion/error gate')
            substitutions = dict(run=str(work), log=str(work / 'run.vcs.log'),
                                 result=str(work / 'numerical.json'))
            run_command([s.format(**substitutions) for s in case['checker']],
                        work, 'NUMERICAL', env, 600)
            numeric = json.loads((work / 'numerical.json').read_text())
            if numeric['state'] != 'PASS':
                raise ValueError('Numerical gate')
            run_command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                         '--require-backend', '--require-axi', '--require-axi-write',
                         '--vector-trace', work / 'vector.csv', '--log', work / 'run.vcs.log',
                         '--simv', simv, '--elf', case['elf'], '--output', work / 'protocol.json'],
                        work, 'PROTOCOL', env, 1200)
            proof = json.loads((work / 'protocol.json').read_text())
            if proof['status'] != 'PASS' or proof['issues'] or any(
                    proof['contract_counts'][k] for k in ('exceptions', 'protocol_errors', 'outstanding')):
                raise ValueError('Protocol/completion gate')
            for field, expected in (('elf_sha256', case['elf_sha256']),
                                    ('simv_sha256', image_pins[str(simv)]),
                                    ('log_sha256', sha(work / 'run.vcs.log')),
                                    ('vector_trace_sha256', sha(work / 'vector.csv'))):
                if proof[field] != expected:
                    raise ValueError('Protocol identity: ' + field)
            result.update(state='PASS', numeric=numeric, independent_protocol_checked=True)
        except Exception as exc:
            result.update(error=repr(exc), state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL')
            stop.set()
        result['wall_seconds'] = time.monotonic() - start
        save(work / 'result.json', result)
        save(work / 'status.json', dict(state=result['state']))
        with lock:
            completed.append(dict(id=case['id'], state=result['state']))
            save(output / 'status.json', dict(state='STOPPING_AFTER_FAILURE' if stop.is_set() else 'RUNNING',
                 total=len(plan['cases']), completed=len(completed), cases=completed))
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=plan['parallel']) as pool:
        results = list(pool.map(one, plan['cases']))
    drift = None
    try:
        verify(pins)
        verify(image_pins)
        verify(json.loads((image / 'source-pins.json').read_text()))
    except Exception as exc:
        drift = repr(exc)
    state = 'PASS' if not drift and all(r['state'] == 'PASS' for r in results) else 'INCOMPLETE'
    save(output / 'result.json', dict(state=state, cases=results, pin_error=drift, image=str(image),
                                     rtl_precheck_only=True, scope=plan['scope']))
    save(output / 'status.json', dict(state=state, total=len(results), completed=len(completed), cases=completed))
    return int(state != 'PASS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'execute', 'status'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', type=Path)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--parallel', type=int, default=4)
    a = p.parse_args()
    out = a.output.resolve()
    if a.action == 'prepare':
        prepare(out, a.image.resolve(), a.manifest.resolve(), a.parallel)
        return 0
    if a.action == 'status':
        print((out / 'status.json').read_text())
        return 0
    return execute(out)


if __name__ == '__main__':
    raise SystemExit(main())
