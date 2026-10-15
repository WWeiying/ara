#!/usr/bin/env python3
"""Explicitly gated PIDFD wait then one offline CSV traversal per original case."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORK = HERE.parent/'full_small2_vcs_m6_plan01'
RUN = WORK/'prepared01'
ENTRY = HERE.parent/'full_small2_entry_review01/ENTRY.json'
PLAN_SHA = '7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee'
PARENT_SHA = '59ed91223eb2b925ae518ad81ad4618c118589b43d03bfa0670241da0dd34bf8'
ENTRY_SHA = '88c9d814d713c0095fba0d2bd4e3f5c104795a70605bc8ec739f76eda091b8e3'
LAUNCH_SHA = '06796f330a586cd6e61959987182d8d5e8c1f442c4ebd556cb46b583319cd2cc'
GENERIC = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
PID = 1580624
UNIT = 'ara-arithmetic-full-small2-m6-01.service'
GROUP = '/user.slice/user-1002.slice/user@1002.service/app.slice/'+UNIT
WORKER_PASS = 'PASS_M6_FULL_ORIGINAL_SMALL2_10080_CALLS_NOT_LINUX'
WAIT_SECONDS, AUDIT_SECONDS = 14400, 1800
ABORT = False
TERMINAL_DECIDED = False


def need(ok, why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(pins, skip=()):
    for path, digest in pins.items():
        if path not in skip:
            need(sha(path) == digest, 'Pinned input drift: '+path)


def own_pins(expected):
    need(expected and sha(HERE/'pins.json') == expected, 'Approved auditor pin identity required')
    verify(read(HERE/'pins.json'))


def cancelled():
    need(not ABORT, 'Sticky auditor abort')


def signal_abort(*_):
    global ABORT
    if TERMINAL_DECIDED:
        return
    ABORT = True
    raise InterruptedError('Auditor received termination signal')


def process_identity(argv, group):
    need(group.strip() == '0::'+GROUP, 'Worker cgroup differs')
    need(len(argv) >= 3 and Path(argv[0]).name.startswith('python3') and argv[1] == '-B' and
         Path(argv[2]).resolve() == WORK/'replay.py', 'Worker executable/script differs')
    expected = ['run','--image','/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image',
                '--out',str(RUN),'--plan-sha256',PLAN_SHA,'--authorize-run',
                '--entry-review',str(ENTRY),'--entry-review-sha256',ENTRY_SHA,
                '--parent-review',str(WORK/'parent_review.json'),'--parent-review-sha256',PARENT_SHA]
    need(argv[3:] == expected, 'Actual worker argv/approval identity differs')


def wait_fd(fd, seconds):
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    events = poller.poll(max(0, int(seconds*1000)))
    need(events and all(not flags & select.POLLNVAL for _,flags in events), 'PIDFD timeout/invalid fd')
    need(any(flags & select.POLLIN for _,flags in events), 'PIDFD did not report process exit')


def wait_worker(out):
    need(sha(RUN/'launch.json') == LAUNCH_SHA, 'Actual launch identity')
    launch = read(RUN/'launch.json')
    need(launch['owner']['pid'] == PID and launch['owner']['properties']['Id'] == UNIT and
         launch['owner']['properties']['ControlGroup'] == GROUP and launch['plan_sha256'] == PLAN_SHA,
         'Pinned original worker owner')
    started = time.monotonic()
    try:
        fd = os.pidfd_open(PID)
    except ProcessLookupError:
        need((RUN/'complete.json').is_file(), 'Worker absent without durable terminal; no retry')
        event = dict(mode='already_absent_terminal_present', pid=PID,
                     historical_service_exit_confirmed=False)
    else:
        try:
            proc = Path('/proc')/str(PID)
            poller = select.poll()
            poller.register(fd, select.POLLIN)
            if poller.poll(0):
                need((RUN/'complete.json').is_file(), 'Already exited without terminal')
                event = dict(mode='pidfd_already_exited',pid=PID)
            else:
                # A race with exit fails closed; no reattachment to a reused PID.
                argv = (proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
                group = (proc/'cgroup').read_text()
                process_identity(argv,group)
                stat = (proc/'stat').read_text().rsplit(')',1)[1].split()
                event = dict(mode='pidfd_exit',pid=PID,argv=argv,cgroup=group,
                             start_ticks=int(stat[19]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
                save(out/'attached.json',event)
                wait_fd(fd,WAIT_SECONDS)
        finally:
            os.close(fd)
    cancelled()
    event.update(elapsed_s=time.monotonic()-started,worker_wait_status_unavailable=True,
                 historical_service_exit_confirmed=False)
    save(out/'worker_exit_event.json',event)


def empty_cgroup(root=Path('/sys/fs/cgroup')):
    path = root/GROUP.lstrip('/')
    if not path.exists():
        return dict(state='removed',path=str(path),service_exit_status='UNCONFIRMED')
    files = list(path.rglob('cgroup.procs'))
    need(files and path/'cgroup.procs' in files, 'Unreadable cgroup membership')
    need(all(not p.read_text().strip() for p in files), 'Residual process in worker cgroup')
    events = dict(line.split() for line in (path/'cgroup.events').read_text().splitlines())
    need(events.get('populated') == '0', 'Worker cgroup remains populated')
    return dict(state='empty',path=str(path),service_exit_status='UNCONFIRMED')


def terminal_gate(complete, metadata, summary, cases):
    names = [c['id'] for c in cases]
    need(complete['status'] == WORKER_PASS and complete['plan_sha256'] == PLAN_SHA and
         complete['aborted'] is False and complete['pins_unchanged'] is True and
         type(complete['retries']) is int and complete['retries'] == 0 and
         not complete.get('error') and not complete.get('first_failure'), 'Whole2 terminal is not accepted')
    need(metadata['status'] == 'COMPLETE' and metadata['status_counts'] == {'PASS':2} and
         metadata['tests'] == names and metadata['jobs'] == 2 and metadata['timeout_s'] == 10800 and
         metadata['commit_trace'] is True and metadata['code_coverage'] is False and metadata['completed_at'],
         'Actual runner COMPLETE contract')
    need(complete['results'] == summary and len(summary) == 2 and [r['name'] for r in summary] == names,
         'Exact whole2 result membership')
    for result in summary:
        need(result['status'] == 'PASS' and type(result['returncode']) is int and result['returncode'] == 0 and
             not result['reason'] and 0 <= result['elapsed_s'] <= 10800, 'Actual case exit/budget')


def outcome_gate(outcome, result, command):
    need(outcome['schema'] == 'UNVALIDATED_CHILD_OUTCOME_V2' and outcome['architectural_acceptance'] is False and
         type(outcome['returncode']) is int and outcome['returncode'] == 0 and
         outcome['timed_out'] is False and outcome['failure_seen'] is False and outcome['cancelled'] is False and
         outcome['elapsed_s'] == result['elapsed_s'] and outcome['command'] == command['command'] and
         outcome['cwd'] == command['cwd'], 'Numeric monitor outcome/command is not accepted')


def publish_success(out,value):
    global TERMINAL_DECIDED
    signals = {signal.SIGINT,signal.SIGTERM}
    old = signal.pthread_sigmask(signal.SIG_BLOCK,signals)
    try:
        cancelled()
        need(not signal.sigpending() & signals,'Pending termination at terminal decision')
        save(out/'terminal_candidate.json',value)
        need(not signal.sigpending() & signals,'Termination during terminal publication')
        # Exclusive link is the terminal decision; signals after it are not a late abort.
        os.link(out/'terminal_candidate.json',out/'TERMINAL.json')
        TERMINAL_DECIDED = True
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,old)


def identity(path):
    s = path.stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


class HashLines:
    def __init__(self,path):
        self.file = path.open('rb')
        self.digest = hashlib.sha256()
        self.eof = False
    def __iter__(self): return self
    def __next__(self):
        data = self.file.readline()
        if not data:
            self.eof = True
            raise StopIteration
        self.digest.update(data)
        return data.decode('utf-8')
    def __enter__(self): return self
    def __exit__(self,*_): self.file.close()


def one_pass(path, strict, generic, checkpoint):
    before = identity(path)
    holder = []
    class Input:
        def open(self,**kwargs):
            need(not holder, 'Second raw open refused')
            holder.append(HashLines(path))
            return holder[0]
    class Fanout:
        def __init__(self,stream):
            self.reader = csv.DictReader(stream)
            self.fieldnames = self.reader.fieldnames
            required = {'cycle','event','order','port','trans_id','pc','insn','rd','rd_wdata',
                        'mem_addr','mem_rmask','mem_wmask','mem_wdata','trap'}
            need(self.fieldnames and len(set(self.fieldnames)) == len(self.fieldnames) and
                 required.issubset(self.fieldnames), 'Lossless full RVFI columns required')
            self.count = 0
        def __iter__(self): return self
        def __next__(self):
            row = next(self.reader)
            need(None not in row and all(v is not None for v in row.values()), 'Malformed CSV field count')
            if self.count % 4096 == 0: checkpoint()
            self.count += 1
            strict.consume(row)
            return row
    # This is a private module instance; the frozen generic implementation is unchanged.
    generic.csv = SimpleNamespace(DictReader=Fanout)
    general = generic.validate_trace(Input())
    specific = strict.finish()
    checkpoint()
    need(len(holder) == 1 and holder[0].eof and identity(path) == before, 'Full EOF/immutable single traversal')
    return general,specific,holder[0].digest.hexdigest(),before


def audit(out,pins_sha,event_sha):
    started = time.monotonic()
    own_pins(pins_sha)
    need(sha(out/'worker_exit_event.json') == event_sha, 'Supervisor exit event binding')
    cancelled()
    cgroup = empty_cgroup()
    need(sha(RUN/'plan.json') == PLAN_SHA and sha(ENTRY) == ENTRY_SHA and
         sha(WORK/'parent_review.json') == PARENT_SHA, 'Exact plan/entry/parent')
    plan = read(RUN/'plan.json')
    verify(plan['pins'])
    verify(read(ENTRY)['evidence_pins'])
    complete_path = RUN/'complete.json'
    complete_sha = sha(complete_path)
    complete = read(complete_path)
    metadata,summary = read(RUN/'replay/run.json'),read(RUN/'replay/summary.json')
    terminal_gate(complete,metadata,summary,plan['cases'])
    need(metadata['simv'] == read(Path(plan['image'])/'image.json')['simv'], 'Actual simv metadata')
    approvals = complete['approval_pins']
    need(approvals.get(str(ENTRY)) == ENTRY_SHA and approvals.get(str(WORK/'parent_review.json')) == PARENT_SHA,
         'Terminal exact consumed approvals')
    verify(approvals)
    csvs = {str(RUN/'replay/tests'/c['id']/'commit_trace.csv') for c in plan['cases']}
    evidence = complete['evidence_pins']
    required = {str(RUN/n) for n in ('launch.json','replay/run.json','replay/summary.json')}
    for case in plan['cases']:
        root = RUN/'replay/tests'/case['id']
        required.update(str(root/n) for n in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                                             'child_outcome.unvalidated.json','commit_trace.csv','trace_summary.json','strict_original.json'))
    need(required.issubset(evidence), 'Missing terminal evidence pins')
    verify(evidence,skip=csvs)
    sys.path.insert(0,str(WORK))
    strict_module = load_module('full_small2_terminal_strict',WORK/'checker.py')
    ledger = read(Path(plan['image'])/'image.json')
    reports,stats = [],{}
    # Both numeric outcomes and artifact contracts must pass before opening either CSV.
    for case,result in zip(plan['cases'],summary):
        cancelled()
        root = RUN/'replay/tests'/case['id']
        need(result['artifact_dir'] == str(root), 'Private artifact root differs')
        command = read(root/'command.json')
        outcome = read(root/'child_outcome.unvalidated.json')
        outcome_gate(outcome,result,command)
        need(outcome['command_sha256'] == sha(root/'command.json'), 'Durable command hash')
        strict_module.common.check_artifacts(SimpleNamespace(**dict(result,artifact_dir=root)),
                                            dict(case,original_name=case['id']),ledger)
        spec = plan['specs'][case['shape']]
        strict_module.console_gate((root/'console.log').read_text(),spec['config'])
        need(not strict_module.VETO.search((root/'work/run.vcs.log').read_text()), 'VCS raw failure')
    for case in plan['cases']:
        root = RUN/'replay/tests'/case['id']
        spec = plan['specs'][case['shape']]
        state = strict_module.Strict(spec,read(strict_module.REF/case['shape']/'model.json'))
        generic = load_module('isolated_frozen_trace',GENERIC)
        path = root/'commit_trace.csv'
        save(out/(case['id']+'.parse_started.json'),dict(path=str(path),time=time.time(),single_attempt=True))
        def checkpoint():
            cancelled()
            need(time.monotonic()-started < AUDIT_SECONDS-15, 'Bounded offline audit deadline')
        general,specific,digest,stat = one_pass(path,state,generic,checkpoint)
        need(digest == evidence[str(path)], 'Actual CSV hash differs')
        need(dict(status='VALID',**general) == read(root/'trace_summary.json'), 'Generic full result differs from worker')
        need(specific == read(root/'strict_original.json'), 'Strict full result differs from worker')
        need(general['cvx_exception_count'] == 0, 'CVX exception observed')
        report = dict(case=case['id'],generic=general,strict=specific,raw_sha256=digest,raw_parses=1)
        save(out/(case['id']+'.json'),report)
        reports.append(dict(case=case['id'],calls=specific['calls'],results=specific['results'],guards=specific['guards'],
                            report_sha256=sha(out/(case['id']+'.json')),csv_sha256=digest))
        stats[str(path)] = stat
    need([sum(r[k] for r in reports) for k in ('calls','results','guards')] == [10080,161280,20160], 'Complete source totals')
    verify(plan['pins'])
    verify(approvals)
    verify(evidence,skip=csvs)
    own_pins(pins_sha)
    need(sha(complete_path) == complete_sha and sha(RUN/'plan.json') == PLAN_SHA and
         all(identity(Path(p)) == value for p,value in stats.items()), 'Late terminal/CSV/input drift')
    empty_cgroup()
    cancelled()
    save(out/'candidate_report.json',dict(status='OFFLINE_CHECKS_ACCEPTED_PENDING_ACTUAL_AUDITOR_EXIT',
         plan_sha256=PLAN_SHA,complete_sha256=complete_sha,reports=reports,raw_parses=2,
         reference_raw_parses=0,pins_unchanged=True,cgroup=cgroup,elapsed_s=time.monotonic()-started,
         service_exit_status='UNCONFIRMED_NOT_INFERRED',scope='Full original two architectural source shapes; not Linux/all22'))


def supervisor(pins_sha):
    own_pins(pins_sha)
    out = HERE/'run01'
    out.mkdir()
    save(out/'authorization.json',dict(pins_sha256=pins_sha,wait_seconds=WAIT_SECONDS,audit_seconds=AUDIT_SECONDS,
                                     worker_pid=PID,unit=UNIT,plan_sha256=PLAN_SHA,no_retry=True))
    try:
        wait_worker(out)
        empty_cgroup()
        command = [sys.executable,'-B',str(HERE/'terminal.py'),'--audit-child','--pins-sha256',pins_sha,
                   '--event-sha256',sha(out/'worker_exit_event.json')]
        save(out/'audit_command.json',dict(command=command,timeout_s=AUDIT_SECONDS))
        started = time.monotonic()
        with (out/'audit.log').open('x') as log:
            child = subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            timeout,error = False,None
            try:
                rc = child.wait(timeout=AUDIT_SECONDS)
            except BaseException as exc:
                timeout = isinstance(exc,subprocess.TimeoutExpired)
                error = repr(exc)
                child.kill()
                rc = child.wait()
            save(out/'audit_process_exit.json',dict(returncode=rc,timed_out=timeout,error=error,
                 elapsed_s=time.monotonic()-started,pid=child.pid,attempt=1))
        need(type(rc) is int and rc == 0 and not timeout and error is None, 'Actual offline child did not succeed')
        own_pins(pins_sha)
        cancelled()
        report = read(out/'candidate_report.json')
        need(report['status'] == 'OFFLINE_CHECKS_ACCEPTED_PENDING_ACTUAL_AUDITOR_EXIT', 'Missing completed audit')
        empty_cgroup()
        need(sha(RUN/'complete.json') == report['complete_sha256'], 'Late worker terminal drift')
        publish_success(out,dict(status='INDEPENDENT_FULL_SMALL2_TERMINAL_ACCEPTED',
             plan_sha256=PLAN_SHA,report_sha256=sha(out/'candidate_report.json'),
             actual_audit_exit_sha256=sha(out/'audit_process_exit.json'),raw_parses=2,
             service_exit_status='UNCONFIRMED_NOT_INFERRED',historical_service_exit_confirmed=False))
        return 0
    except BaseException as error:
        save(out/'FIRST_ERROR.json',dict(status='NOT_ACCEPTED_NO_AUTORETRY',error=repr(error),time=time.time()))
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--authorize-event-worker',action='store_true')
    modes.add_argument('--audit-child',action='store_true')
    p.add_argument('--pins-sha256',required=True)
    p.add_argument('--event-sha256')
    args = p.parse_args()
    for number in (signal.SIGTERM,signal.SIGINT): signal.signal(number,signal_abort)
    if args.audit_child:
        need(args.event_sha256, 'Actual supervisor event required')
        audit(HERE/'run01',args.pins_sha256,args.event_sha256)
        return 0
    return supervisor(args.pins_sha256)


if __name__ == '__main__':
    sys.exit(main())
