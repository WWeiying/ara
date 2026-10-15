#!/usr/bin/env python3
"""Owned whole59 adapter; prepare is dry-run only, worker requires terminal review."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HOME = HERE.parent
REVIEW = HOME.parent
BASE = REVIEW / 'integration'
sys.path.insert(0, str(BASE))
import replay_candidate04_regression_final as existing
import csv_adapter

base = existing.base
read, sha, require = base.read, base.sha, base.require
PREDECESSOR = HOME / 'launch_plan01/plan.json'
PREDECESSOR_SHA = 'b3e931fff67e87861b51052a5948c1c34a6da548f11bfde846663f6b12ebe630'
IMAGE = existing.original.IMAGE
OLD = REVIEW / 'whole_register_original/vcs_candidate04_01'
OLD_UNIT = 'ara-whole1134-candidate04-01.service'
LIB = REVIEW / 'masked_translation/indexed_review/sv39'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scheduler = load(LIB / 'scheduler.py', 'whole59_owned_scheduler')
tail = load(LIB / 'live_tail.py', 'whole59_live_tail')


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def publish(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, suffix='.pending') as f:
            temporary = Path(f.name)
            json.dump(value, f, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


class Abort(scheduler.Abort):
    def __init__(self):
        super().__init__()
        self.terminal = False

    def stop(self, reason):
        with self.lock:
            if not self.terminal:
                super().stop(reason)


class Terminal:
    def __init__(self, abort, deadline, now=time.monotonic):
        self.abort, self.deadline, self.now = abort, deadline, now
        self.closed = False

    def timeout(self):
        with self.abort.lock:
            if not self.closed:
                self.abort.stop(dict(error='Pair 660s deadline including CSV checker'))

    def guard(self):
        with self.abort.lock:
            if self.now() >= self.deadline:
                self.timeout()
            require(self.abort.reason is None, 'Cancelled/deadline before pair acceptance')

    def accept(self, path, result):
        with self.abort.lock:
            self.guard()
            publish(path, result)
            self.guard()
            self.closed = True


def command(out, pair=None, execute=False):
    cases = read(out / 'plan.json')['cases'] if (out / 'plan.json').exists() else read(PREDECESSOR)['cases']
    cmd = ['/usr/bin/python3', '-B', str(BASE / 'run.py'), 'run', '--image', str(IMAGE),
           '--programs', str(out / 'programs'), '--out',
           str(out / 'dryrun' if pair is None else out / 'pairs' / f'pair{pair:02d}' / 'run'),
           '--jobs', '6' if pair is None else '1', '--timeout', '600']
    for c in cases if pair is None else [cases[pair]]:
        cmd += ['--case', c['id']]
    return cmd + (['--execute'] if execute else [])


def checker(case, spike=False):
    d = Path(case['elf']).parent
    backend = 'spike' if spike else 'soc'
    return csv_adapter.Checker(case, read(d / (backend+'.symbols.json')), read(d / (backend+'.targets.json')),
                               (d / (backend+'.dis')).read_text(), spike)


def console_ok(text, case):
    for marker in case['pass_markers']:
        require(text.count(marker) == 1, 'Missing/duplicate exact marker: ' + marker)
    require('Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text, 'Missing simulator success')
    require(not re.search(r'\b(?:[A-Z_]*FAIL[A-Z_]*|CANCELLED|TIMEOUT|SIGTERM|SIGINT|UVM_FATAL)\b|Error-\[|Fatal[-:]|BOARD_REPLAY_TRAP', text),
            'Failure/cancel marker despite PASS')


def validate_case(out, case, rc, image, cmd):
    d = out / 'pairs' / f"pair{case['pair']:02d}" / 'run'
    t = d / 'tests' / case['id']
    summary, run, inputs = read(d / 'summary.json'), read(d / 'run.json'), read(t / 'inputs.json')
    require(rc == 0 and len(summary) == 1 and summary[0]['name'] == case['id'] and
            summary[0]['status'] == 'PASS' and summary[0]['returncode'] == 0 and
            0 < summary[0]['elapsed_s'] < 600, 'Runner failure/deadline/incomplete case')
    require(run['status'] == 'COMPLETE' and run['tests'] == [case['id']] and run['jobs'] == 1 and
            run['timeout_s'] == 600 and run['seed'] == 1 and run['commit_trace'] and run['input_snapshots'] and
            run['simv'] == image['simv'] and run['invocation'] == cmd[2:], 'Run metadata differs')
    require(inputs['binary'] == dict(source=case['elf'], path=str(t / 'input.elf'), sha256=case['sha256']) and
            sha(t / 'input.elf') == case['sha256'], 'Private ELF identity differs')
    require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), 'Actual image differs')
    expected = [image['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD='+str(t/'input.elf'),
                '+TESTCASE='+case['id'], '+NO_FSDB', '+COMMIT_TRACE='+str(t/'commit_trace.csv')]
    require(read(t / 'command.json') == dict(command=expected, cwd=str(t / 'work')), 'Actual simulator command differs')
    console_ok((t / 'console.log').read_text(), case)
    return summary


def run_pair(out, case, image, abort):
    number = case['pair']
    d = out / 'pairs' / f'pair{number:02d}'
    d.mkdir()
    k = checker(case)
    started = time.monotonic()
    terminal = Terminal(abort, started+660)
    events = tail.DirectoryEvents(d)
    first = True
    process = timer = None
    rc = None
    cmd = command(out, number, True)
    save(d / 'command.json', cmd)

    def failure(error):
        record = dict(pair=number, error=str(error), last_pc=k.last_pc, cycle=k.cycle,
                      order=k.order, calls=len(k.calls), output_byte_checks=k.reads)
        with abort.lock:
            abort.stop(record)
            if not (d / 'firstfailure.json').exists():
                save(d / 'firstfailure.json', record)

    def line(text):
        nonlocal first
        values = next(csv.reader([text]))
        if first:
            require(values == csv_adapter.FIELDS, 'Wrong live CSV header')
            first = False
        else:
            require(len(values) == len(csv_adapter.FIELDS), 'Malformed CSV row')
            terminal.guard()
            k.row(dict(zip(csv_adapter.FIELDS, values)))

    try:
        with (d / 'worker.log').open('x') as log:
            process = abort.launch(number, lambda: subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, cwd=base.shared.ROOT if hasattr(base.shared, 'ROOT') else BASE))
            timer = threading.Timer(max(0, terminal.deadline-time.monotonic()), terminal.timeout)
            timer.daemon = True
            timer.start()
            rc = tail.wait_append(process, events, d/'run/tests'/case['id']/'commit_trace.csv', line, failure)
        terminal.guard()
        analysis = k.finish()
        summary = validate_case(out, case, rc, image, cmd)
        terminal.guard()
        result = dict(status='PASS', pair=number, returncode=rc, analysis=analysis,
                      summary=summary, elapsed_s=time.monotonic()-started)
        terminal.accept(d / 'complete.json', result)
    except Exception as error:
        failure(error)
        if process is None:
            events.close()
        result = dict(status='NOT_ACCEPTED', pair=number, returncode=rc, error=str(error),
                      elapsed_s=time.monotonic()-started)
        publish(d / 'complete.json', result)
    finally:
        with abort.lock:
            terminal.closed = True
        if timer:
            timer.cancel()
            timer.join()
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                scheduler.cancel_process(process)
                process.wait(timeout=20)
        abort.remove(number)
    return result


def process_snapshot():
    rows = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != os.getuid():
                continue
            comm = (p/'comm').read_text().strip()
            cgroup = (p/'cgroup').read_text()
            try:
                argv = (p/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            except PermissionError:
                require(comm != 'simv' and OLD_UNIT not in cgroup, 'Potential owned/simv process inaccessible')
                continue
        except (FileNotFoundError, ProcessLookupError):
            continue
        rows.append(dict(pid=int(p.name), comm=comm, cgroup=cgroup, argv=argv))
    return rows


def admission(roster):
    rows = process_snapshot()
    require(not any(OLD_UNIT in r['cgroup'] or str(OLD) in r['argv'] for r in rows), 'Old whole1134 still owns processes')
    live = [r for r in rows if r['comm'] == 'simv']
    units = [r['unit'] for r in roster]
    require(len(units) == len(set(units)) and OLD_UNIT not in units, 'Duplicate/unreleased old reservation')
    spare = 0
    for reservation in roster:
        require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', reservation['unit']) and
                type(reservation['slots']) is int and 1 <= reservation['slots'] <= 24, 'Invalid reservation')
        actual = sum('/'+reservation['unit'] in r['cgroup'] for r in live)
        spare += max(0, reservation['slots']-actual)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])*1024
    require(len(live)+spare+6 <= 24 and available >= 32*1024**3, 'Capacity unavailable; refuse once without retry')
    return dict(simv=live, roster=roster, spare_reserved=spare, own_reserved=6,
                total=len(live)+spare+6, available_bytes=available)


def terminal_gate(review, plan):
    ref = review['whole1134_acceptance']
    require(sha(Path(ref['path'])) == ref['sha256'], 'Terminal acceptance identity differs')
    a = read(ref['path'])
    require(a['status'] == 'WHOLE1134_STRICT_TERMINAL_PASS' and a['output'] == str(OLD) and
            a['image_sha256'] == plan['image_sha256'] and a['groups'] == 20 and a['cases'] == 1134 and a['skips'] == 366 and
            a['firstfailure'] is None and a['pins_unchanged'] is True, 'Missing strict whole1134 acceptance')
    require(a['service'] == dict(unit=OLD_UNIT, Result='success', ExecMainStatus=0, MainPID=0), 'Old service not accepted terminal')
    evidence = a['evidence_pins']
    required = [OLD/'complete.json', OLD/'plan.json', OLD/'replay/summary.json', OLD/'replay/run.json']
    for n in range(20):
        required += [OLD/'replay/tests'/f'whole_op{n:02d}'/name for name in
                     ('inputs.json', 'input.elf', 'command.json', 'console.log', 'commit_trace.csv')]
    require(all(str(p) in evidence for p in required), 'Strict terminal evidence not fully bound')
    base.verify_pins(evidence)
    oldplan, oldend = read(OLD/'plan.json'), read(OLD/'complete.json')
    require(sha(OLD/'plan.json') == a['plan_sha256'] == oldend['plan_sha256'], 'Old plan differs')
    require(oldend['status'] == 'PASS_1134_IN_20_PARTITIONS' and oldend['image_sha256'] == plan['image_sha256'] and
            oldend['pins_unchanged'] is True and oldend.get('firstfailure') is None and
            not list(OLD.rglob('firstfailure.json')), 'Old campaign failure/abort')
    names = {f'whole_op{n:02d}' for n in range(20)}
    for records in (oldend['results'], read(OLD/'replay/summary.json')):
        require(len(records) == 20 and {r['name'] for r in records} == names and
                all(r['status'] == 'PASS' and r['returncode'] == 0 and 0 < r['elapsed_s'] < 5400 for r in records),
                'Old results incomplete/timeout')
    base.verify_pins(oldplan['pins'])
    state = subprocess.check_output(['systemctl', '--user', 'show', OLD_UNIT, '-p', 'LoadState', '-p', 'ActiveState',
                                    '-p', 'MainPID', '-p', 'Result', '-p', 'ExecMainStatus'], text=True, timeout=10)
    fields = dict(line.split('=', 1) for line in state.splitlines())
    require(fields['ActiveState'] == 'inactive' and fields['MainPID'] == '0', 'Old unit still live/failed')
    require(fields['LoadState'] in ('loaded', 'not-found'), 'Unknown old state')
    if fields['LoadState'] == 'loaded':
        require(fields['Result'] == 'success' and fields['ExecMainStatus'] == '0', 'Old service failed')
    return dict(acceptance=ref, pins=evidence, service_observation=fields)


def publish_campaign(out, results, abort, plan, deadline, post, now=time.monotonic):
    signals = {signal.SIGTERM, signal.SIGINT}
    oldmask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    try:
        with abort.lock:
            if now() >= deadline:
                abort.stop(dict(error='Campaign 3000s deadline'))
            for s in signal.sigpending() & signals:
                abort.stop(dict(signal=int(s)))
            passed = post == 'UNCHANGED' and abort.reason is None and set(results) == set(range(59)) and all(
                r['status'] == 'PASS' and r['returncode'] == 0 and r['elapsed_s'] < 660 for r in results.values())
            end = dict(status='M4_MISSING59_BOUNDARY_SUPPLEMENT_PASS' if passed else 'NOT_ACCEPTED',
                       results=results, firstfailure=abort.reason, post_hashes=post,
                       plan_sha256=sha(out/'plan.json'), image_sha256=plan['image_sha256'], scope=plan['scope'])
            publish(out/'complete.json', end)
            for s in signal.sigpending() & signals:
                abort.stop(dict(signal=int(s)))
            if now() >= deadline:
                abort.stop(dict(error='Campaign deadline during publication'))
            if passed and abort.reason is not None:
                end.update(status='NOT_ACCEPTED', firstfailure=abort.reason)
                publish(out/'complete.json', end)
                passed = False
            abort.terminal = True
            return int(not passed)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, oldmask)


def prepare(out):
    require(not out.exists() and sha(PREDECESSOR) == PREDECESSOR_SHA, 'Fresh successor output / sealed predecessor required')
    plan = read(PREDECESSOR)
    base.verify_pins(plan['pins'])
    image, _, _ = existing.original.identity()
    require(image['files'] == plan['image_files'], 'M4 image differs')
    host = read(HERE/'host01/complete.json')
    require(host['status'] == 'HOST_ALL59_CSV_AND_NEGATIVES_PASS_NOT_DUT' and host['pairs'] == list(range(59)), 'Host all59 not PASS')
    base.verify_pins(host['pins'])
    out.mkdir()
    (out/'programs').mkdir()
    (out/'bindings').mkdir()
    (out/'pairs').mkdir()
    paths = [Path(__file__), HERE/'csv_adapter.py', HERE/'test_adapter.py', HERE/'host_check.py',
             HERE/'README.md', HERE/'host01/complete.json', HERE/'host01/tests.log', PREDECESSOR,
             LIB/'scheduler.py', LIB/'live_tail.py', csv_adapter.ROOT/'verification/coverage/scoped_rv64c_memory.py']
    for c in plan['cases']:
        d = Path(c['elf']).parent
        paths += [d/'soc.dis', d/'spike.dis']
    plan['pins'].update({str(p): sha(p) for p in paths})
    binding = {os.path.relpath(p, out/'bindings'): h for p, h in plan['pins'].items()
               if str(HOME/'prepared02') in p and Path(p).suffix in ('.c', '.S', '.h', '.ld')}
    save(out/'bindings/provenance.json', dict(scope='Unchanged precompiled pair source binding; no build', files=binding))
    programs = {c['id']: dict(path=c['elf'], sha256=c['sha256'], cases=[c['id']], pass_markers=c['pass_markers']) for c in plan['cases']}
    save(out/'programs/programs.json', dict(backend='vcs-soc', prepared=str(out/'bindings'),
         provenance_sha256=sha(out/'bindings/provenance.json'), programs=programs))
    cmd = command(out)
    save(out/'dryrun_command.json', cmd)
    with (out/'dryrun.log').open('x') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True)
    dry = read(out/'dryrun/summary.json')
    require(len(dry) == 59 and {x['name'] for x in dry} == set(programs) and all(x['status'] == 'DRY_RUN' for x in dry), 'Dryrun differs')
    for p in (out/'bindings/provenance.json', out/'programs/programs.json', out/'dryrun_command.json', out/'dryrun/summary.json'):
        plan['pins'][str(p)] = sha(p)
    plan.update(status='WORKER_CSV_READY_NOT_LAUNCHED', executable_worker_ready=True,
                predecessor_plan_sha256=PREDECESSOR_SHA, orchestration='whole59_successor02',
                remaining_before_launch=['Parent pinned strict whole1134 acceptance and slot release',
                                         'Parent review/trigger; one-shot capacity admission'])
    base.verify_pins(plan['pins'])
    save(out/'plan.json', plan)
    save(out/'review.template.json', dict(parent_authorized=False, plan_sha256=sha(out/'plan.json'),
         image_sha256=plan['image_sha256'], jobs=6,
         whole1134_acceptance=dict(path='PARENT_SUPPLIES_STRICT_ACCEPTANCE_JSON', sha256='PARENT_SUPPLIES_SHA256'),
         reserved_units=[]))
    save(out/'preflight.json', dict(status='READY_NOT_LAUNCHED', plan_sha256=sha(out/'plan.json'),
         cases=59, jobs=6, image_sha256=plan['image_sha256'], host_checks=host['status'], VCS_started=False))
    print(json.dumps(read(out/'preflight.json'), indent=2), flush=True)


def worker(out, review_path, authorized):
    require(authorized and review_path is not None, 'Explicit parent review and authorization required')
    require(not (out/'worker.json').exists(), 'No duplicate launch/retry')
    plan, review = read(out/'plan.json'), read(review_path)
    require(plan['status'] == 'WORKER_CSV_READY_NOT_LAUNCHED' and plan['orchestration'] == 'whole59_successor02', 'Wrong worker plan')
    require(review['parent_authorized'] is True and review['plan_sha256'] == sha(out/'plan.json') and
            review['image_sha256'] == plan['image_sha256'] == existing.original.IMAGE_SHA and review['jobs'] == 6, 'Review binding differs')
    require(plan['cases'] == read(PREDECESSOR)['cases'] and plan['jobs'] == 6, 'Original59 scope/budgets changed')
    base.verify_pins(plan['pins'])
    image, _, _ = existing.original.identity()
    gate = terminal_gate(review, plan)
    resources = admission(review['reserved_units'])
    review_sha = sha(review_path)
    save(out/'worker.json', dict(pid=os.getpid(), started_unix=time.time(), plan_sha256=sha(out/'plan.json'),
         review_sha256=review_sha, gate=gate, resources=resources))
    started = time.monotonic()
    deadline = started+3000
    abort = Abort()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda n, f: abort.stop(dict(signal=n)))
    timer = threading.Timer(3000, lambda: abort.stop(dict(error='Campaign 3000s deadline')))
    timer.daemon = True
    timer.start()
    results = {}
    pending = list(plan['cases'])
    post = 'UNCHANGED'
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            running = {}
            while running or pending:
                with abort.lock:
                    while pending and len(running) < 6 and abort.reason is None:
                        c = pending.pop(0)
                        running[pool.submit(run_pair, out, c, image, abort)] = c['pair']
                if not running:
                    break
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    number = running.pop(future)
                    try:
                        result = future.result()
                    except Exception as error:
                        result = dict(status='NOT_ACCEPTED', pair=number, error=str(error))
                    results[number] = result
                    if result['status'] != 'PASS':
                        abort.stop(dict(pair=number, result=result))
        for c in pending:
            results[c['pair']] = dict(status='CANCELLED_NOT_LAUNCHED', pair=c['pair'])
        base.verify_pins(plan['pins'])
        base.verify_pins(gate['pins'])
        require(sha(review_path) == review_sha and existing.original.identity()[0] == image, 'Post-run identity drift')
    except Exception as error:
        post = str(error)
        abort.stop(dict(error=post))
    finally:
        timer.cancel()
        timer.join()
    return publish_campaign(out, results, abort, plan, deadline, post)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'worker'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--review', type=Path)
    p.add_argument('--authorize-run', action='store_true')
    a = p.parse_args()
    out = a.out.resolve()
    require(out.is_relative_to(HERE) and out != HERE, 'Fresh output must be in successor02')
    if a.action == 'prepare':
        prepare(out)
    else:
        raise SystemExit(worker(out, a.review, a.authorize_run))
