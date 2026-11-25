#!/usr/bin/env python3
"""Shared, fail-closed RTL/GLS admission. Paused by default; no legacy worker edits."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
LOCK = OUT / '.power_gls_20261117_slots.lock'
STATE = OUT / 'power_shared_slots_20261117_v4_01'
ADAPTER = OUT / 'power_gls_20261117_q8_smoke_02/inputs/gate_run.py'
ADAPTER_SHA = 'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d'
CAP = 4


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    tmp.replace(path)


def adapter():
    require(sha(ADAPTER) == ADAPTER_SHA, 'Frozen legacy reservation adapter drift')
    spec = importlib.util.spec_from_file_location('shared_slots_legacy', ADAPTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def locked(path=LOCK):
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def start_token(pid):
    fields = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
    return fields[19]  # Linux starttime; PID alone is not a process identity.


def analyze(rows, legacy, leases=()):
    physical = {pid: ppid for pid, (ppid, argv) in rows.items()
                if argv and Path(argv[0]).name == 'simv'}
    future, held, blockers, legacy_owners = 0, 0, [], []
    modern = set()
    for lease in leases:
        if lease['state'] == 'FINISHED':
            continue
        owner = lease['owner_pid']
        if owner not in rows:
            blockers.append(dict(kind='UNRECONCILED_LEASE_OWNER_EXIT', lease=lease['id']))
        else:
            modern.add(owner)
        child = lease.get('child_pid')
        matched = child in physical and physical[child] == owner and rows[child][1] == lease['command']
        if child in physical and not matched:
            blockers.append(dict(kind='LEASE_CHILD_PID_REUSE_OR_COMMAND_DRIFT', lease=lease['id']))
        if not matched:
            held += 1
    for pid, (ppid, argv) in rows.items():
        if not argv or pid in modern:
            continue
        names = [Path(a).name for a in argv]
        if 'execute' in argv and any(n.startswith('gate_') and n.endswith('.py') for n in names):
            # An old watchdog cannot be upgraded by acquiring its lock alone.
            legacy_owners.append(pid)
        if 'after_compile.py' in names:
            blockers.append(dict(kind='LEGACY_FUTURE_DISPATCH_CONTROLLER', pid=pid))
        workers = [Path(a) for a in argv if Path(a).name in legacy.KNOWN_DISPATCHERS]
        precheck = any(n.startswith('precheck') and n.endswith('.py') for n in names)
        if 'execute' not in argv or not precheck:
            continue
        if not workers:
            blockers.append(dict(kind='UNKNOWN_DISPATCHER', pid=pid, argv=argv))
            continue
        try:
            require(len(workers) == 1 and argv.count('--output') == 1, 'Ambiguous legacy dispatcher')
            output = Path(argv[argv.index('--output')+1])
            reserve = legacy.dispatcher_reservation(pid, workers[0], output, rows, physical)
            active = sum(parent == pid for parent in physical.values())
            require(reserve >= active, 'Legacy reservation below actual occupancy')
            future += reserve-active
        except (OSError, KeyError, ValueError, IndexError, TypeError, AttributeError) as exc:
            blockers.append(dict(kind='UNVERIFIABLE_DISPATCH_RESERVATION', pid=pid, error=repr(exc)))
    if legacy_owners:
        blockers.append(dict(kind='LEGACY_GLS_WATCHDOG_ACTIVE_MIGRATION_BARRIER', pids=legacy_owners))
    return dict(physical_simv_pids=sorted(physical), physical_simv_count=len(physical),
        legacy_future_reservations=future, acquired_lease_without_visible_child=held,
        committed_slots=len(physical)+future+held, blockers=blockers,
        scope='Same UID process cohort, matching frozen gate scheduler; argv executable identity, not comm',
        cap=CAP, shared_lock=str(LOCK))


def read_leases(state):
    return [json.loads(p.read_text()) for p in sorted((state/'leases').glob('*.json'))]


def inspect(state=STATE, legacy=None):
    legacy = legacy or adapter()
    leases = read_leases(state)
    rows = legacy.process_snapshot()
    result = analyze(rows, legacy, leases)
    for lease in leases:
        if lease['state'] != 'FINISHED' and lease['owner_pid'] in rows:
            try:
                require(start_token(lease['owner_pid']) == lease['owner_starttime'], 'Lease PID reused')
            except (OSError, ValueError) as exc:
                result['blockers'].append(dict(kind='LEASE_PROCESS_IDENTITY', id=lease['id'], error=repr(exc)))
    return result


def admission(policy, snapshot):
    require(policy == dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=False),
            'Admission paused or policy invalid')
    require(not snapshot['blockers'], 'Unresolved scheduling protocol/identity blockers')
    require(snapshot['committed_slots'] < CAP, 'No unreserved shared simulator slot')


def initialize(state=STATE):
    # No resume operation is performed by init or audit, even if re-invoked.
    with locked():
        require(not state.exists(), 'Fresh scheduler state required')
        state.mkdir()
        (state/'leases').mkdir()
        save(state/'policy.json', dict(protocol='RTL_GLS_SHARED_SLOTS_V4', cap=4, paused=True))
        save(state/'source-pins.json', {str(Path(__file__).resolve()): sha(__file__),
            str(ADAPTER): ADAPTER_SHA})


def run(kind, argv, work, env, timeout, pins, state=STATE):
    """Common future RTL/GLS launch primitive. Both consumers must use this API.

    It launches only the actual simv, never an opaque worker that may dispatch
    later. Legacy GLS watchdogs must drain before migration; no compatibility
    claim is made for sealed consumers that still use a different protocol.
    """
    require(kind in ('RTL', 'GLS') and 1 <= timeout <= 14400 and Path(argv[0]).name == 'simv',
            'Bounded actual simulator command required')
    legacy = adapter()
    with locked():
        policy = json.loads((state/'policy.json').read_text())
        current = inspect(state, legacy)
        admission(policy, current)
        for name, digest in pins.items():
            require(sha(name) == digest, 'Dispatch input drift: '+name)
        require(pins.get(str(argv[0])) == sha(argv[0]), 'Simulator not pinned')
        pid = os.getpid()
        lease_id = '%s-%d-%d' % (kind, pid, time.time_ns())
        lease_path = state/'leases'/(lease_id+'.json')
        lease = dict(id=lease_id, kind=kind, owner_pid=pid, owner_starttime=start_token(pid),
            child_pid=None, state='LAUNCHING', command=list(map(str, argv)),
            acquired=time.time(), admission_snapshot=current)
        save(lease_path, lease)
        try:
            handle = (work/'simulator.console.log').open('x')
            try:
                proc = subprocess.Popen(list(map(str, argv)), cwd=work, env=env,
                    stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
            finally:
                handle.close()
            lease.update(child_pid=proc.pid, state='RUNNING')
            save(lease_path, lease)
        except BaseException:
            lease.update(state='FINISHED', launch_failed=True)
            save(lease_path, lease)
            raise
    try:
        rc = proc.wait(timeout=timeout)
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        raise
    finally:
        with locked():
            lease.update(state='FINISHED', returncode=proc.returncode, finished=time.time())
            save(lease_path, lease)
    return rc


def audit(output, state=STATE):
    require(not output.exists() and output.parent == OUT, 'Fresh owned audit output required')
    output.mkdir()
    test = Path(__file__).with_name('test_shared_slots_v4.py')
    with (output/'host-tests.log').open('x') as log:
        subprocess.run(['/usr/bin/python3', '-B', str(test), '-v'], stdout=log,
                       stderr=subprocess.STDOUT, timeout=60, check=True)
    with locked():
        report = inspect(state)
        report.update(policy=json.loads((state/'policy.json').read_text()),
                      new_simulations_started=0, existing_workers_modified=False,
                      active_consumers_migrated=False)
        save(output/'scheduler-audit.json', report)
    evidence = {}
    for name in ('power_gls_20261117_q8_smoke_02', 'power_gls_20261117_q8_capture_01'):
        for file in ('attempt.json', 'result.json', 'status.json'):
            p = OUT/name/file
            evidence[str(p)] = dict(sha256=sha(p), mtime_ns=p.stat().st_mtime_ns,
                                    content=json.loads(p.read_text()))
    for mode in ('native', 'rvv'):
        root = OUT/('power_precheck_20261117_m4_compact_%s_v3_01' % mode)
        for p in (root/'attempt.json', root/'runs'/('power_q4_m4_compact_'+mode)/'dispatch.json'):
            evidence[str(p)] = dict(sha256=sha(p), mtime_ns=p.stat().st_mtime_ns,
                                    content=json.loads(p.read_text()))
    save(output/'incident-evidence.json', evidence)
    timeline = sorted([dict(path=p, file_mtime_ns=v['mtime_ns']) for p, v in evidence.items()
                       if p.endswith('attempt.json') or p.endswith('dispatch.json') or
                       ('power_gls_' in p and p.endswith('result.json'))], key=lambda row: row['file_mtime_ns'])
    save(output/'root-cause.json', dict(
        state='ROOT_CAUSE_CONFIRMED_ADMISSION_PAUSED', timeline=timeline,
        v3_lock=str(OUT/'.power-vcs-slots-20261117.lock'), gate_lock=str(LOCK),
        unknown_v3_is_full_capacity_sentinel=True, sentinel_is_not_physical_process_count=True,
        cause='Starting unknown precheck_power_v3.py execute trips frozen GLS conservative reservation '
              'watchdog before v3 simv Popen; independent lock and physical-only comm count were unsafe.',
        correction='One shared lock, explicit physical/future/lease accounting, explicit blockers, '
                   'PID/command identity, paused admission, legacy GLS migration barrier.',
        deployment='New common launch primitive only; no sealed running worker patched or automatically migrated.',
        old_failed_reports_preserved=True, new_vcs_launched=0, automatic_restart=False))
    pins = {str(Path(__file__).resolve()): sha(__file__), str(test): sha(test), str(ADAPTER): ADAPTER_SHA}
    pins.update({p: v['sha256'] for p, v in evidence.items()})
    for name, digest in pins.items():
        require(sha(name) == digest, 'Audit input changed: '+name)
    save(output/'source-pins.json', pins)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('init-paused', 'audit'))
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.action == 'init-paused':
        initialize()
    else:
        require(a.output is not None, '--output required')
        print(json.dumps(audit(a.output.resolve()), indent=2))


if __name__ == '__main__':
    main()
