#!/usr/bin/env python3
"""Run finite, pinned operator cases, at most four VCS workers, then summarize."""
import argparse
import concurrent.futures
import csv
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


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def save(p, value):
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(p)


def verify(pins):
    for name, value in pins.items():
        if sha(name) != value:
            raise RuntimeError('Pinned input changed: ' + name)


def command(argv, cwd, logfile, env, timeout, statefile, phase):
    with logfile.open('x') as f:
        p = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env,
                             stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        save(statefile, dict(state=phase, child_pid=p.pid, started=time.time(), command=list(map(str, argv))))
        try:
            rc = p.wait(timeout=timeout)
        except BaseException:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL); p.wait()
            raise
    if rc:
        raise RuntimeError('Command exit ' + str(rc) + ': ' + str(logfile))


def prepare(out, soc, manifest, parallel):
    if out.exists() or out.parent != OUT or not out.name.startswith('operator_campaign_'):
        raise ValueError('Use fresh operator_campaign_* output')
    cases = json.loads(manifest.read_text())['cases']
    ids = [c['id'] for c in cases]
    if not cases or len(ids) != len(set(ids)) or not all(re.fullmatch(r'[A-Za-z0-9_-]+', n) for n in ids):
        raise ValueError('Empty or invalid case identities')
    if not 1 <= parallel <= 4:
        raise ValueError('Concurrency must be 1..4')
    build = json.loads((soc / 'build.json').read_text())
    if build['state'] != 'CURRENT_OPERATOR_SOC_BUILT_NOT_EXECUTED' or not build['post_pins_match']:
        raise ValueError('Current complete build required')
    pins = json.loads((soc / 'source-pins.json').read_text()) | build['image_pins']
    pins[str(soc / 'build.json')] = sha(soc / 'build.json')
    pins[str(manifest)] = sha(manifest)
    for c in cases:
        if not 1 <= c.get('timeout_seconds', 10800) <= 10800:
            raise ValueError('Invalid timeout')
        if sha(c['elf']) != c['elf_sha256']:
            raise ValueError('ELF identity')
        extra = json.loads(Path(c['source_pins']).read_text())
        extra[str(Path(c['source_pins']))] = sha(c['source_pins'])
        extra[c['elf']] = c['elf_sha256']
        for p, h in extra.items():
            if p in pins and pins[p] != h:
                raise ValueError('Conflicting pin ' + p)
        pins.update(extra)
        if not isinstance(c['checker'], list) or not c['checker']:
            raise ValueError('Independent numerical checker missing')
    verify(pins)
    out.mkdir(); (out / 'inputs').mkdir(); (out / 'runs').mkdir()
    script = out / 'inputs/campaign.py'
    script.write_bytes(Path(__file__).read_bytes()); pins[str(script)] = sha(script)
    plan = dict(soc=str(soc), parallel=parallel, cases=cases, configuration=build['configuration'],
                environment=json.loads((soc / 'plan.json').read_text())['environment'],
                simv=build['simv'], stop_on_failure=True, automatic_retry=False)
    save(out / 'plan.json', plan); pins[str(out / 'plan.json')] = sha(out / 'plan.json')
    save(out / 'source-pins.json', pins)
    save(out / 'status.json', dict(state='PREPARED_NOT_RUN', total=len(cases), completed=0))


def successful_log(log):
    text = log.read_text(errors='strict')
    if 'Core Test *** SUCCESS ***' not in text or re.search(r'Fatal:|Error:|Error-|\bFAILED\b', text):
        raise ValueError('Firmware success/assertion gate failed')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b', line) and not re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*', line):
            raise ValueError('UVM error')


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/campaign.py' or (out / 'attempt.json').exists():
        raise ValueError('Frozen one-shot worker required')
    save(out / 'attempt.json', dict(owner_pid=os.getpid(), started=time.time()))
    plan = json.loads((out / 'plan.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    verify(pins)
    env = dict(plan['environment'], PYTHONPATH=str(Path(plan['soc']) / 'source/verification'),
               PYTHONDONTWRITEBYTECODE='1')
    stop, lock, results = threading.Event(), threading.Lock(), []

    def run(c):
        if stop.is_set():
            return dict(id=c['id'], state='NOT_DISPATCHED_AFTER_FAILURE')
        work = out / 'runs' / c['id']; work.mkdir()
        result = dict(id=c['id'], category=c['category'], state='FAIL', whole_model=False)
        t = time.monotonic()
        try:
            # Full source audit once per batch; check each ELF and image at dispatch.
            verify({c['elf']: c['elf_sha256'], plan['simv']: pins[plan['simv']]})
            argv = [plan['simv'], '-no_save', '-l', str(work / 'run.vcs.log'),
                '+PRELOAD=' + c['elf'], '+TESTCASE=operator_' + c['id'], '+NO_FSDB', '+NO_INSTR_TRACE',
                '+VECTOR_TRACE=' + str(work / 'vector.csv'), '+COMMIT_TRACE=' + str(work / 'commit.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000',
                *c.get('plusargs', [])]
            command(argv, work, work / 'console.log', env, c.get('timeout_seconds', 10800),
                    work / 'status.json', 'VCS_RUNNING')
            successful_log(work / 'run.vcs.log')
            substitutions = dict(run=str(work), log=str(work / 'run.vcs.log'), result=str(work / 'numerical.json'))
            argv = [s.format(**substitutions) for s in c['checker']]
            command(argv, work, work / 'numerical.log', env, 600, work / 'status.json', 'NUMERICAL_CHECK')
            numeric = json.loads((work / 'numerical.json').read_text())
            if numeric.get('state') != 'PASS':
                raise ValueError('Numerical/work/guard gate did not PASS')
            argv = [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write',
                '--vector-trace', str(work / 'vector.csv'), '--log', str(work / 'run.vcs.log'),
                '--simv', plan['simv'], '--elf', c['elf'], '--output', str(work / 'protocol.json')]
            command(argv, work, work / 'protocol.log', env, 1200, work / 'status.json', 'PROTOCOL_CHECK')
            proof = json.loads((work / 'protocol.json').read_text())
            if proof['status'] != 'PASS' or proof['issues'] or proof['elf_sha256'] != c['elf_sha256'] or \
                proof['simv_sha256'] != pins[plan['simv']] or proof['log_sha256'] != sha(work / 'run.vcs.log') or \
                proof['vector_trace_sha256'] != sha(work / 'vector.csv') or \
                any(proof['contract_counts'][k] != 0 for k in ('exceptions', 'protocol_errors', 'outstanding')):
                raise ValueError('Independent protocol / completion identity failed')
            artifacts = {str(p):sha(p) for p in work.iterdir() if p.is_file() and
                         p.name not in ('status.json', 'result.json')}
            result.update(state='PASS', measured=numeric, independent_protocol_checked=True,
                          checked_artifact_hashes=artifacts)
        except Exception as exc:
            result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
            stop.set()
        result['wall_seconds'] = time.monotonic() - t
        save(work / 'result.json', result)
        save(work / 'status.json', dict(state=result['state'], child_pid=None))
        with lock:
            results.append(result)
            save(out / 'status.json', dict(state='STOPPING_AFTER_FAILURE' if stop.is_set() else 'RUNNING',
                completed=len(results), total=len(plan['cases']), pass_count=sum(x['state']=='PASS' for x in results),
                cases=[dict(id=x['id'], state=x['state']) for x in results]))
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=plan['parallel']) as pool:
        all_results = list(pool.map(run, plan['cases']))
    drift = None
    try:
        verify(pins)
    except Exception as exc:
        drift = repr(exc)
    report = dict(state='PASS' if not drift and all(x['state']=='PASS' for x in all_results) else 'INCOMPLETE',
        cases=all_results, post_source_image_pins_match=drift is None, pin_error=drift,
        configuration=plan['configuration'], whole_model=False)
    save(out / 'result.json', report)
    save(out / 'status.json', dict(state=report['state'], completed=len(results), total=len(plan['cases'])))
    with (out / 'summary.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=('id', 'state', 'category', 'wall_seconds', 'error'))
        writer.writeheader()
        for x in all_results:
            writer.writerow({k:x.get(k, '') for k in writer.fieldnames})
    print(json.dumps(report), flush=True)
    return report['state'] != 'PASS'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare','execute','status'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--soc', type=Path)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--parallel', type=int, default=4)
    a = p.parse_args(); out = a.output.resolve()
    if a.action == 'prepare':
        prepare(out, a.soc.resolve(), a.manifest.resolve(), a.parallel)
        return 0
    if a.action == 'status':
        print((out / 'status.json').read_text()); return 0
    return execute(out)


if __name__ == '__main__':
    raise SystemExit(main())
