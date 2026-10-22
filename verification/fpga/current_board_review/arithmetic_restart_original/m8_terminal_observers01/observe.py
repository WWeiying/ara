#!/usr/bin/env python3
"""One identity acquisition, then inotify waits; never opens any CSV."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
A = HERE.parent
WAIT = A.parent / 'wait_terminal.py'
WAIT_SHA = 'cbc78208bc6464aad86a485f296006f17a31b272d9ef8332617a98caf2b45dd4'
CONFIG = {
    'e8_m8': dict(directory='full_e8_m8_block_vcs_m9_plan01', pid=3036940,
        unit='ara-arithmetic-original-e8-m8-full4095-m9-01.service',
        plan_sha='d5499f1b6d2db2f9cc8cd9300caf13fc571f7f9c2738a94f29c0fc66b8da0339'),
    'e16_m8': dict(directory='full_e16_m8_block_vcs_m9_plan01', pid=3062361,
        unit='ara-arithmetic-original-e16-m8-full4095-m9-01.service',
        plan_sha='35a5f9956dd7c0955bcb5dce6e352d0620d08b4b0d2bd223f30a3a2aac14379e'),
}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    need(path.suffix != '.csv' and path.stat().st_size < 10000000, 'Metadata-only input')
    return json.loads(path.read_text())


def sha(path):
    need(path.suffix != '.csv' and path.stat().st_size < 10000000, 'No CSV/large file hashing')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def duration(text):
    units = {'us': .000001, 'ms': .001, 's': 1, 'min': 60, 'h': 3600, 'd': 86400}
    parts = re.findall(r'(\d+(?:\.\d+)?)(us|ms|min|s|h|d)', text)
    need(parts and ''.join(a+b for a,b in parts) == text.replace(' ', ''), 'Unknown systemd duration')
    return sum(float(number) * units[unit] for number, unit in parts)


def proc(pid):
    root = Path('/proc') / str(pid)
    stat = (root / 'stat').read_text().rsplit(') ', 1)[1].split()
    return dict(pid=pid, start_ticks=int(stat[19]), state=stat[0],
        argv=[s.decode() for s in (root / 'cmdline').read_bytes().split(b'\0') if s],
        cgroup=(root / 'cgroup').read_text(), exe=os.readlink(root / 'exe'))


def acquire(config, out, source, plan):
    names = ('Id','LoadState','ActiveState','SubState','MainPID','ExecMainPID','ControlGroup',
        'ExecMainCode','ExecMainStatus','Result','ExecMainStartTimestampMonotonic',
        'ExecMainExitTimestampMonotonic','RuntimeMaxUSec','TimeoutStopUSec')
    command = ['systemctl','--user','show','--no-pager','--property='+','.join(names),config['unit']]
    env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    query = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    save(out/'systemctl_once.json', dict(command=command, actual_returncode=query.returncode,
        stdout=query.stdout, stderr=query.stderr, observed_at=time.time(), observed_monotonic=time.monotonic(),
        XDG_RUNTIME_DIR=env['XDG_RUNTIME_DIR'], DBUS_SESSION_BUS_ADDRESS=env['DBUS_SESSION_BUS_ADDRESS']))
    need(query.returncode == 0 and not query.stderr, 'User-manager query failed; no GC default inference')
    lines = query.stdout.splitlines()
    props = dict(line.split('=',1) for line in lines)
    need(len(props) == len(lines) and set(props) == set(names) and props['Id'] == config['unit'] and
         props['LoadState'] == 'loaded', 'Exact loaded service, not collected defaults')
    need(duration(props['RuntimeMaxUSec']) == plan['service_timeout_s'] == 13200, 'Original runtime limit must remain13200')
    start = int(props['ExecMainStartTimestampMonotonic']) / 1000000
    need(start > 0 and int(props['ExecMainPID']) == config['pid'], 'Actual original service generation')
    deadline = start + 13200
    fd = None
    handle = None
    if int(props['MainPID']) == config['pid']:
        need(props['ActiveState'] in ('active','deactivating') and props['ControlGroup'], 'Actual owned lifecycle')
        first = proc(config['pid'])
        need(first['cgroup'].splitlines() == ['0::'+props['ControlGroup']] and
             props['ControlGroup'].endswith('/'+config['unit']), 'Actual exact worker cgroup')
        argv = first['argv']
        need(str(source.parent/'replay.py') in argv and 'run' in argv and
             argv[argv.index('--out')+1] == str(source) and
             argv[argv.index('--plan-sha256')+1] == config['plan_sha'], 'Actual worker argv/run/plan')
        try:
            fd = os.pidfd_open(config['pid'])
            second = proc(config['pid'])
            need(second['start_ticks'] == first['start_ticks'] and second['argv'] == first['argv'] and
                 second['cgroup'] == first['cgroup'], 'PID generation changed while acquiring handle')
            handle = dict(identity=first, pidfd_acquired=True, pidfd=fd)
        except (ProcessLookupError, FileNotFoundError):
            handle = dict(identity=first, pidfd_acquired=False, reason='Exited during handle acquisition; real terminal receipts still required')
    else:
        need(int(props['MainPID']) == 0 and props['SubState'] in ('exited','dead','failed','stop-post'),
             'Unexpected service owner/lifecycle')
        handle = dict(pidfd_acquired=False, reason='Already no main process; real terminal receipts required')
    save(out/'attachment.json', dict(status='EVENT_OBSERVER_ATTACHED_NOT_ACCEPTANCE', config=config,
        own_pid=os.getpid(), source=str(source), plan_sha256=config['plan_sha'], properties=props, handle=handle,
        original_start_monotonic=start, absolute_deadline_monotonic=deadline,
        remaining_s=max(0, deadline-time.monotonic()), original_runtime_s=13200,
        source_runtime_modified=False, CSV_reads=0, polls=0, wait_helper_sha256=sha(WAIT)))
    return deadline, fd


def wait_file(path, deadline, out, name):
    remaining = deadline - time.monotonic()
    # At expiry only already-published facts may be consumed. No extension/retry.
    if remaining <= 0:
        save(out/(name+'.wait.json'), dict(already_published=path.is_file(), deadline_expired=True))
        return path.is_file()
    command = [sys.executable,'-B',str(WAIT),str(path),'--timeout',str(remaining)]
    start = time.monotonic()
    with (out/(name+'.wait.log')).open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        rc = child.wait()
    save(out/(name+'.wait.json'), dict(command=command,pid=child.pid,actual_wait_returncode=rc,
        elapsed_s=time.monotonic()-start,remaining_bound_s=remaining))
    return rc == 0


def classify(out, source, root, config, plan, fd):
    complete, service, monitor, collected, collector_exit = [read(p) for p in (
        source/'complete.json',source/'service_exit.json',root/'child_outcome.unvalidated.json',
        source/'collector_result.json',source/'collector_exit.json')]
    result = dict(status='TERMINAL_REQUIRES_REVIEW', CSV_reads=0, semantic_parses=0,
        simulator_runs=0, source=str(source), original_complete=complete, original_service=service,
        actual_monitor=monitor, original_collector=collected, actual_collector_exit=collector_exit,
        pidfd_exit_observed=bool(select.select([fd],[],[],0)[0]) if fd is not None else None,
        evidence_pins={str(p):sha(p) for p in (source/'plan.json',source/'complete.json',
            source/'service_exit.json',root/'child_outcome.unvalidated.json',root/'command.json',
            source/'collector_result.json',source/'collector_exit.json')})
    need(sha(source/'plan.json') == config['plan_sha'], 'Late original plan drift')
    need(complete['plan_sha256'] == config['plan_sha'] and len(complete['results']) == 1,
         'Actual original terminal membership')
    row = complete['results'][0]
    if type(monitor.get('returncode')) is not int or monitor['returncode'] != 0 or any(
            monitor.get(k) is not False for k in ('timed_out','failure_seen','cancelled')):
        result.update(status='SIMULATOR_NOT_CLEAN_REPORT_FIRSTCAUSE',firstcause=row.get('reason') or complete.get('error'))
    elif row['status'] == 'ERROR' and complete['status'] == 'NOT_PASS':
        prefix = 'Postcheck ValueError: Missing necessary architectural owner '
        reason = row.get('reason','')
        if reason.startswith(prefix):
            error = ast.literal_eval(reason[len(prefix):])
            need(set(error) == {'insn','pc','retire_order','call','helper_index','kind','required','arch_order','alloc','done'},
                 'Exact owner diagnostic schema')
            spec = plan['specs'][plan['cases'][0]['shape']]
            target = spec['backend']['helpers']['op_19'][8]
            matched = (error['insn'] == target['insn'] == 0x38813c57 and error['pc'] == target['pc'] and
                error['call'] == 1200 and error['helper_index'] == 8 and error['kind'] == 'target' and
                error['required'] is True and error['alloc'] == error['done'] == 0 and
                type(error['retire_order']) is int and error['retire_order'] >= 0 and
                type(error['arch_order']) is int and error['arch_order'] >= 0)
            command = read(root/'command.json')
            matched = matched and monitor['command_sha256'] == sha(root/'command.json') and (
                monitor['command'] == command['command'] and monitor['cwd'] == command['cwd'])
            matched = matched and row['name'] == plan['cases'][0]['id'] and row['returncode'] == 0 and (
                0 < row['elapsed_s'] == monitor['elapsed_s'] <= 10800 and complete['retries'] == 0)
            matched = matched and service['kind'] == 'SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT' and (
                [service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')] == ['exit-code','exited','1'])
            if matched:
                result.update(status='EXACT_VI2_OWNER_REJECTION_ELIGIBLE_FOR_OWN_PREPARE_NOT_ACCEPTED',
                    firstcause=reason,owner_error=error,closed_audit_allowed=False)
            else:
                result.update(firstcause=reason,exact_owner_match=False)
        else:
            result['firstcause'] = reason or complete.get('error')
    else:
        result['firstcause'] = row.get('reason') or complete.get('error') or 'Terminal available; independent acceptance not inferred'
    result['finished'] = time.time()
    save(out/'terminal_notice.json', result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shape',choices=CONFIG,required=True);args=parser.parse_args()
    config=CONFIG[args.shape];out=HERE/args.shape;out.mkdir(exist_ok=True)
    source=A/config['directory']/'prepared01'
    fd=None
    try:
        need(not (out/'attachment.json').exists(),'No duplicate attachment')
        need(sha(WAIT)==WAIT_SHA and sha(source/'plan.json')==config['plan_sha'],'Pinned waiter/source plan')
        plan=read(source/'plan.json');need(len(plan['cases'])==1,'Exact single case')
        root=source/'replay/tests'/plan['cases'][0]['id']
        deadline,fd=acquire(config,out,source,plan)
        targets=[('numeric',root/'child_outcome.unvalidated.json'),('complete',source/'complete.json'),
            ('service_exit',source/'service_exit.json'),('collector_result',source/'collector_result.json'),
            ('collector_exit',source/'collector_exit.json')]
        for name,path in targets:
            if not wait_file(path,deadline,out,name):
                published={label:read(p) for label,p in targets if p.is_file()}
                save(out/'terminal_notice.json',dict(status='ABSOLUTE_DEADLINE_REACHED_NOT_ACCEPTANCE',
                    missing=name,absolute_deadline_monotonic=deadline,published_facts=published,
                    CSV_reads=0,semantic_parses=0,source_runtime_modified=False))
                return 2
            if name=='numeric':
                numeric=read(path)
                if numeric.get('returncode') != 0 or any(numeric.get(k) is not False for k in ('timed_out','failure_seen','cancelled')):
                    save(out/'numeric_firstcause_notice.json',dict(status='NUMERIC_FAILURE_NO_RETRY',actual=numeric,CSV_reads=0))
        terminal=classify(out,source,root,config,plan,fd)
        if terminal['status']=='EXACT_VI2_OWNER_REJECTION_ELIGIBLE_FOR_OWN_PREPARE_NOT_ACCEPTED':
            save(out/'PREPARE_REQUEST.json',dict(status='OWN_TEMPLATE_HOST_PLAN_REQUESTED_NO_AUDIT',
                terminal_notice_sha256=sha(out/'terminal_notice.json'),source=str(source),shape=args.shape,
                template=str(A/'full_m8_slideup_owner_templates01/owner_delta.py'),
                template_sha256=sha(A/'full_m8_slideup_owner_templates01/owner_delta.py'),
                independent_entry_required=True,closed_audit_allowed=False))
        return 0
    except BaseException as error:
        save(out/'observer_failure.json',dict(status='OBSERVATION_FAILED_NOT_DUT_RESULT',
            firstcause=type(error).__name__+': '+str(error),CSV_reads=0,simulator_runs=0,finished=time.time()))
        return 1
    finally:
        if fd is not None:os.close(fd)


if __name__=='__main__':raise SystemExit(main())
