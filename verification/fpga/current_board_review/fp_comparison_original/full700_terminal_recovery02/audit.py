"""Closed original700 metadata recovery; no simulation or semantic CSV reread."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'full700_m9_terminal_collector01'
UNIT = 'ara-fp-alias-original700-m9-01.service'
OUT = HERE / 'run01'


def load(path):
    spec = importlib.util.spec_from_file_location('retained_original700_collector', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


c = load(OLD / 'collect.py')
read, sha, save, require = c.read, c.sha, c.save, c.require


def service_gate(p):
    require(p['Id'] == UNIT and p['LoadState'] == 'loaded' and
            p['RemainAfterExit'] == 'yes' and p['ActiveState'] == 'active' and
            p['SubState'] == 'exited' and p['MainPID'] == '0' and
            p['Result'] == 'success' and p['ExecMainCode'] == '1' and
            p['ExecMainStatus'] == '0', 'Retained actual producer exit0 required')
    require(0 < int(p['ExecMainStartTimestampMonotonic']) <
            int(p['ExecMainExitTimestampMonotonic']), 'Actual monotonic exit timestamps')


def query(name):
    keys = ('Id,LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,'
            'ExecMainStatus,ControlGroup,RemainAfterExit,ExecStart,'
            'ExecMainStartTimestamp,ExecMainExitTimestamp,'
            'ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic')
    command = ['systemctl', '--user', 'show', UNIT, '--property=' + keys]
    started = time.time()
    p = subprocess.run(command, env=c.bus(), text=True, capture_output=True, timeout=10)
    receipt = dict(command=command, actual_returncode=p.returncode, stdout=p.stdout,
                   stderr=p.stderr, query_started=started, query_finished=time.time(),
                   provenance='INDEPENDENT_LIVE_QUERY_OF_RETAINED_EXITED_UNIT_NOT_HOOK_OR_GC')
    save(OUT / name, receipt)
    require(p.returncode == 0 and not p.stderr.strip(), 'Actual user-manager query failed')
    fields = dict(line.split('=', 1) for line in p.stdout.splitlines())
    require(set(fields) == set(keys.split(',')), 'Incomplete actual service properties')
    service_gate(fields)
    return fields


def closure_gate(service, state, matches, unknown):
    service_gate(service)
    require(state in ('removed', 'empty') and not matches and not unknown,
            'Unknown closure or residual owned processes')


def closure(ready, service, name):
    group = ready['worker_cgroup']
    root = Path('/sys/fs/cgroup') / group.lstrip('/')
    require(root.name == UNIT and group.startswith('/user.slice/'), 'Exact original cgroup')
    raced = False
    if not root.exists():
        state = 'removed'
    else:
        try:
            files = list(root.rglob('cgroup.procs'))
            require(root / 'cgroup.procs' in files, 'Incomplete cgroup tree')
            require(all(not p.read_text().strip() for p in files), 'Cgroup still owns processes')
            state = 'empty'
        except FileNotFoundError:
            require(not root.exists(), 'Partial cgroup disappearance with live root')
            state, raced = 'removed', True
    matches, unknown, examined = [], [], 0
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            groups = (proc / 'cgroup').read_text().splitlines()
            command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            examined += 1
            owns_group = any((g := line.split(':', 2)[-1]) == group or
                             g.startswith(group + '/') for line in groups)
            owns_args = str(c.RUN) in command
            if owns_group or owns_args:
                matches.append(dict(pid=int(proc.name), groups=groups, command=command))
        except FileNotFoundError:
            continue
        except (PermissionError, OSError) as error:
            unknown.append(dict(pid=proc.name, error=repr(error)))
    record = dict(original_group=group, state=state, removal_race_handled=raced,
                  all_proc_examined=examined, matches=matches, unknown=unknown,
                  observed_at=time.time())
    save(OUT / name, record)
    closure_gate(service, state, matches, unknown)
    return record


def local_negatives():
    p = dict(Id=UNIT, LoadState='loaded', RemainAfterExit='yes', ActiveState='active',
             SubState='exited', MainPID='0', Result='success', ExecMainCode='1',
             ExecMainStatus='0', ExecMainStartTimestampMonotonic='10',
             ExecMainExitTimestampMonotonic='20')
    closure_gate(p, 'removed', [], [])
    closure_gate(p, 'empty', [], [])
    rejected = 0
    for updates in ({'LoadState': 'not-found'}, {'ExecMainCode': '0'},
                    {'ExecMainStatus': '17'}, {'MainPID': '123'},
                    {'ExecMainExitTimestampMonotonic': '0'}):
        try:
            closure_gate(dict(p, **updates), 'removed', [], [])
        except ValueError:
            rejected += 1
        else:
            raise ValueError('Missed exit negative')
    for state, matches, unknown in [('removed', [{'pid': 1}], []),
                                     ('removed', [], ['permission']), ('unknown', [], [])]:
        try:
            closure_gate(p, state, matches, unknown)
        except ValueError:
            rejected += 1
        else:
            raise ValueError('Missed closure negative')
    return dict(positive=2, negative=rejected, semantic_CSV_reads=0)


def audit():
    service = query('producer_service_before.json')
    ready = read(OLD / 'READY.json')
    before = closure(ready, service, 'closure_before.json')
    require('FileNotFoundError' in read(OLD / 'run01/STOPPED.json')['error'], 'Original failure identity')
    old_log = (OLD / 'service.log').read_text()
    require('group = base.empty_cgroup' in old_log and 'root.rglob' in old_log and
            not (OLD / 'run01/attempt.json').exists() and not (OLD / 'run01/audit.log').exists(),
            'Old collector must have stopped before semantic audit')
    save(OUT / 'local_checks.json', local_negatives())
    c.ready_gate(sha(OLD / 'READY.json'))
    w, _, _ = c.modules()
    plan = read(c.RUN / 'plan.json')
    w.terminal_plan_gate(c.RUN, c.PLAN, w.IMAGE)
    w.authorization_gate(c.PLAN, c.WORK / 'ENTRY.json', c.ENTRY)
    complete = read(c.RUN / 'complete.json')
    complete_sha = sha(c.RUN / 'complete.json')
    root = c.RUN / 'replay/tests' / w.NAME
    ledger = read(w.IMAGE / 'image.json')
    result = c.success_gate(w, complete, root, ledger, service)
    require(result.elapsed_s == read(root / 'child_outcome.unvalidated.json')['elapsed_s'],
            'Monitor and producer elapsed disagreement')
    service_elapsed = (int(service['ExecMainExitTimestampMonotonic']) -
                       int(service['ExecMainStartTimestampMonotonic'])) / 1e6
    require(result.elapsed_s <= service_elapsed <= w.OUTER, 'Actual child/service budgets')
    invocation = read(c.RUN / 'launch_invocation.json')
    launch = read(c.RUN / 'launch.json')
    require(launch['owner']['pid'] == ready['worker_pid'] and
            launch['owner']['properties']['ControlGroup'] == ready['worker_cgroup'],
            'Original PID/cgroup identity')
    actual_argv = shlex.split(service['ExecStart'].split('argv[]=', 1)[1].split(' ;', 1)[0])
    command = invocation['command']
    require(actual_argv == ready['worker_command'] and
            command[command.index(actual_argv[0]):] == actual_argv and
            '--unit=' + UNIT in command and '--property=RemainAfterExit=yes' in command and
            '--property=RuntimeMaxSec=9000' in command and
            invocation['plan_sha256'] == c.PLAN and invocation['review_sha256'] == c.ENTRY and
            invocation['retries'] == 0 and read(c.RUN / 'launch_process_exit.json')['returncode'] == 0,
            'Actual retained ExecStart differs from original launch argv/approval')
    w.common.check_artifacts(result, plan['cases'][0], ledger)
    for path in (root / 'console.log', root / 'work/run.vcs.log'):
        w.checker.console_gate(path.read_text())
    original = read(root / 'strict_original.json')
    strict, generic, protocol = (original[k] for k in ('strict', 'generic', 'protocol'))
    require(strict['status'] == 'FULL_ORIGINAL700_STRICT_ACCEPTED_NOT_FULL_PARENT', 'Producer strict status')
    require([strict[k] for k in ('target_calls', 'full_result_bit_checks', 'guard_checks',
            'returned_vstart_zero', 'returned_flags_checked', 'helper_instructions')] ==
            [700, 358400, 1400, 700, 700, 12880], 'Full original700 oracle counts')
    calls = strict['calls']
    expected = read(w.PREP / 'prepared01/source_budget_gate.json')['mapping']['call_sequence']
    require(len(calls) == len(expected) == 700, 'Original700 membership')
    for n, (a, b) in enumerate(zip(calls, expected), 1):
        require(a['ordinal'] == n and [a[k] for k in ('op', 'vl', 'mode', 'sticky', 'vstart')] ==
                [b[k] for k in ('op', 'vl', 'mask', 'sticky', 'vstart')] and a['reads'] == 195,
                'Original call order/complete read counts')
    offloads = strict['retired_offloads']
    require(len(offloads) == 6303 and sum(x['backend_required'] for x in offloads) == 3396,
            'All required backend owners including targets')
    require(generic['cvx_exception_count'] == generic['cvx_replay_count'] ==
            generic['arch_request_replay_count'] == 0 and
            generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] == 3396 and
            generic['cvx_request_count'] == generic['cvx_response_count'] ==
            generic['architecture_request_count'] == 6303 and
            generic['retire_count'] == strict['retired'], 'Producer protocol accounting')
    require(protocol == dict(offloads=6303, backend_arches=3396, no_replay=True) and
            read(root / 'trace_summary.json') == dict(status='VALID', **generic), 'Generic/strict binding')
    raw = root / 'commit_trace.csv'
    identity = c.base.raw_identity(raw)
    pins = dict(ready['pins'])
    for path, digest in complete['evidence_pins'].items():
        require(path not in pins or pins[path] == digest, 'Conflicting artifact pin')
        pins[path] = digest
    require(pins[str(raw)] == original['csv_sha256'], 'Strict CSV identity differs from producer pins')
    for path in (c.RUN / 'complete.json', c.WORK / 'ENTRY.json', OLD / 'READY.json',
                 OLD / 'run01/STOPPED.json', OLD / 'run01/attached.json', OLD / 'service.log',
                 Path(__file__).resolve()):
        pins[str(path)] = sha(path)
    c.verify(pins)
    require(c.base.raw_identity(raw) == identity, 'CSV changed during hashing')
    after_service = query('producer_service_after.json')
    after = closure(ready, after_service, 'closure_after.json')
    require(service == after_service and sha(c.RUN / 'complete.json') == complete_sha,
            'Producer identity/complete drift during audit')
    for name in ('producer_service_before.json', 'producer_service_after.json',
                 'closure_before.json', 'closure_after.json', 'local_checks.json'):
        pins[str(OUT / name)] = sha(OUT / name)
    save(OUT / 'evidence_pins.json', pins)
    save(OUT / 'result.json', dict(status='PASS_INDEPENDENT_METADATA_TERMINAL_ORIGINAL700_M9',
        acceptance_basis='Frozen producer full semantic strict+generic PASS independently bound to actual numeric/exit/raw-veto/pins; no second semantic CSV audit',
        semantic_CSV_reparses=0, raw_hash_only=True, original_collector_remains_NOT_ACCEPTED=True,
        original_collector_root_cause='Cgroup removal raced exists/rglob after pidfd closure, before audit',
        plan_sha256=c.PLAN, entry_sha256=c.ENTRY, complete_sha256=complete_sha,
        child_returncode=result.returncode, child_elapsed_s=result.elapsed_s,
        actual_service_elapsed_s=service_elapsed, producer_service=service, actual_worker_argv=actual_argv,
        scope='700 contiguous original calls/699 predecessors; not full17920 or Linux',
        calls=700, result_bits=358400, guards=1400, flags=700, vstarts=700,
        helper_instructions=12880, required_owners=3396, generic=generic,
        csv_sha256=original['csv_sha256'], csv_bytes=identity[2],
        evidence_pins=len(pins), evidence_pins_sha256=sha(OUT / 'evidence_pins.json'),
        pins_unchanged=True, no_DUT_reference_build=True, retries=0))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--child', action='store_true')
    a = p.parse_args()
    if a.child:
        try:
            audit()
            return 0
        except BaseException as error:
            save(OUT / 'STOPPED.json', dict(status='NOT_ACCEPTED', first_error=repr(error)))
            raise
    OUT.mkdir()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--child']
    save(OUT / 'command.json', dict(command=command, timeout_s=180, script_sha256=sha(__file__)))
    started = time.monotonic()
    timed = False
    with (OUT / 'audit.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
    save(OUT / 'actual_wait.json', dict(pid=child.pid, returncode=rc, timed_out=timed,
         elapsed_s=time.monotonic() - started, command=command))
    result = OUT / 'result.json'
    accepted = rc == 0 and not timed and result.exists() and read(result)['status'].startswith('PASS_')
    save(OUT / 'TERMINAL.json', dict(status='PASS_METADATA_RECOVERY' if accepted else 'NOT_ACCEPTED',
        actual_wait_sha256=sha(OUT / 'actual_wait.json'), result_sha256=sha(result) if result.exists() else None,
        semantic_CSV_reparses=0, no_simulation=True))
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
