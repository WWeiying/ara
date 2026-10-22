"""Bounded, fail-closed admission for completed, possibly collected user units."""
import os
from pathlib import Path
import re
import stat
import subprocess
import time

import replay_restart_successor as old

require, sha, read, prior, GATHER = old.require, old.sha, old.read, old.prior, old.GATHER
FIELDS = {'Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlPID', 'ControlGroup'}


def bus_environment(runtime=None):
    uid = os.getuid()
    runtime = Path(f'/run/user/{uid}') if runtime is None else Path(runtime)
    directory, bus = runtime.stat(), (runtime / 'bus').stat()
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == uid and
            directory.st_mode & 0o077 == 0, 'Unsafe or wrong-owner user runtime')
    require(stat.S_ISSOCK(bus.st_mode) and bus.st_uid == uid, 'User bus is not an owned socket')
    env = prior.shared.environment()
    env.update(XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'))
    return env


def parse_unit(unit, result):
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', unit), 'Invalid dependency unit')
    fields = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition('=')
        require(separator and key in FIELDS and key not in fields, 'Malformed/duplicate unit property')
        fields[key] = value
    require(set(fields) == FIELDS and fields['Id'] == unit, 'Incomplete/wrong unit response')
    require(fields['MainPID'] == fields['ControlPID'] == '0' and fields['ControlGroup'] == '',
            'Dependency still owns PID or cgroup')
    terminal_state = (fields['ActiveState'], fields['SubState'])
    if fields['LoadState'] == 'not-found':
        require(terminal_state == ('inactive', 'dead') and result.returncode in (0, 1),
                'Not-found unit lacks complete inactive state')
        require(result.stderr.strip() in ('', f'Unit {unit} could not be found.'),
                'Not-found response also contains a query/bus error')
    else:
        require(fields['LoadState'] == 'loaded' and result.returncode == 0 and not result.stderr.strip()
                and terminal_state in (('inactive', 'dead'), ('failed', 'failed')),
                'Active/unknown/error unit response')
    return dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr, properties=fields)


def query_unit(unit):
    command = ['systemctl', '--user', 'show', unit, '--property=' + ','.join(sorted(FIELDS)), '--no-pager']
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=5, check=False, env=bus_environment())
    return parse_unit(unit, result)


def absence(units, proc_root=Path('/proc'), cgroup_root=Path('/sys/fs/cgroup')):
    """Check all processes, not just simv, and reject even empty unit cgroups."""
    names = set(units)
    require(names and all(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', n) for n in names), 'Invalid units')
    require((cgroup_root / 'cgroup.controllers').read_text().strip(), 'Unreadable/non-v2 cgroup mount')
    owned, directories = [], []
    examined = 0
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            text = (proc / 'cgroup').read_text()
        except (FileNotFoundError, ProcessLookupError):
            require(not proc.exists(), 'Missing cgroup for an existing process')
            continue
        examined += 1
        require(text.strip(), 'Empty process cgroup response')
        for line in text.splitlines():
            fields = line.split(':', 2)
            require(len(fields) == 3 and fields[0].isdigit() and fields[2].startswith('/'),
                    'Malformed process cgroup')
            matches = names.intersection(Path(fields[2]).parts)
            if matches:
                owned.append(dict(pid=int(proc.name), units=sorted(matches), cgroup=fields[2]))
    def failed(error):
        raise error
    for path, dirs, _ in os.walk(cgroup_root, onerror=failed, followlinks=False):
        for name in names.intersection(dirs):
            directories.append(str(Path(path) / name))
    require(not owned and not directories, 'Dependency process/cgroup remains: ' + repr((owned, directories)))
    return dict(processes_examined=examined, owned_processes=owned, unit_cgroups=directories, time=time.time())


def completed_dependencies(records, units):
    final_plan_path = prior.FINAL38 / 'plan.json'
    final_plan = read(final_plan_path)
    final = records['final38_terminal']
    require(prior.completed38(final_plan, final) and final.get('finished', 0) > 0 and
            final['plan_sha256'] == sha(final_plan_path), '38 is not exact terminal PASS')
    gather_plan_path = GATHER / 'plan.json'
    plan = read(gather_plan_path)
    gather, worker = records['gather_terminal'], records['gather_worker_exit']
    rows = gather.get('results', [])
    require(gather['status'] == 'PASS_8_ACCEPTED_PLUS_75_SOURCE_SINGLES_CANDIDATE04' and
            gather.get('finished', 0) > 0 and worker.get('finished', 0) > 0 and
            gather['plan_sha256'] == worker['plan_sha256'] == sha(gather_plan_path), 'Gather is not sealed terminal PASS')
    require(worker['runner_returncode'] == 0 and worker['error'] is None and
            len(rows) == len(plan['names']) == len(plan['remaining_source_names']) == 75 and
            {r['name'] for r in rows} == set(plan['names']) and
            all(r['status'] == 'PASS' and r['returncode'] == 0 for r in rows), 'Gather worker/membership incomplete')
    require(plan['unit'] == units['gather'] and plan['image_sha256'] == prior.IMAGE_SHA, 'Wrong Gather unit/image')
    return dict(final38_plan_sha256=sha(final_plan_path), gather_plan_sha256=sha(gather_plan_path))


def gates(review, plan_sha):
    require(review.get('parent_authorized') is True and review.get('plan_sha256') == plan_sha and
            review.get('image_sha256') == prior.IMAGE_SHA and review.get('jobs') == 2, 'Parent approval missing/wrong')
    require(review.get('old38_reservation_accounting_confirmed') is True, 'Reservation coordination not confirmed')
    evidence, records = review['evidence'], {}
    expected = {'final38_terminal': prior.FINAL38 / 'complete.json', 'gather_terminal': GATHER / 'complete.json',
                'gather_worker_exit': GATHER / 'worker_exit.json'}
    require(set(evidence) == set(expected) | {'nf8_initial_admission'}, 'All gate evidence required')
    for name, entry in evidence.items():
        path = Path(entry['path']).resolve()
        require(name not in expected or path == expected[name], 'Wrong terminal evidence path')
        require(sha(path) == entry['sha256'], 'Evidence changed: ' + name)
        records[name] = read(path)
    units = review['units']
    # Validate all hashes and exact completed records before interpreting rc1.
    completed = completed_dependencies(records, units)
    nf8 = records['nf8_initial_admission']
    ng = nf8['gate']
    require(nf8['jobs'] == 8 and nf8['reserved_through_pilot'] == 8 and nf8['start_unix'] > 0 and
            ng['own_reserved'] == 8 and ng['cap'] == 24 and ng['total_live_plus_reserved'] <= 24 and
            ng['mem_available_bytes'] >= 32 * 1024**3, 'NF8 initial admission not established')
    require(ng['units'] == {n: units[{'parent38': 'final38', 'nf7': 'nf7', 'gather': 'gather', 'whole': 'whole'}[n]]
                           for n in ('parent38', 'nf7', 'gather', 'whole')}, 'Units differ from actual NF8 admission')
    dependencies = {n: query_unit(units[n]) for n in ('gather', 'final38')}
    empty = absence([units[n] for n in dependencies])
    records['dependency_admission'] = dict(terminal_plans=completed, units=dependencies, absence=empty)
    return records
