#!/usr/bin/env python3
"""Fixed host-startup diagnostic; unchanged binary and RTL watchdog."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
OLD = HERE / 'measurement01'
OUT = HERE / 'startup_diagnostic01'
VCS = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, obj):
    with p.open('x') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


def snapshot(pid):
    root = Path('/proc') / str(pid)
    data = {'pid': pid}
    for name in ('stat', 'status', 'wchan', 'cmdline', 'syscall', 'task/%d/children' % pid):
        try:
            data[name] = (root / name).read_text().replace('\0', ' ')
        except OSError as e:
            data[name] = repr(e)
    try:
        data['fds'] = {p.name: os.readlink(p) for p in (root / 'fd').iterdir()}
    except OSError as e:
        data['fds'] = repr(e)
    children = data.get('task/%d/children' % pid, '')
    data['children'] = [snapshot(int(x)) for x in children.split() if x.isdigit()]
    return data


def main():
    OUT.mkdir(exist_ok=False)
    pinned = [OLD / 'simv', OLD / 'result.json', OLD / 'pins.json', Path(__file__)]
    pinned += sorted(p for p in (OLD / 'simv.daidir').rglob('*') if p.is_file())
    pins = {str(p): sha(p) for p in pinned}
    frozen = json.loads((OLD / 'pins.json').read_text())['files']
    assert all(sha(OLD / 'frozen' / p) == h for p, h in frozen.items())
    save(OUT / 'input_pins.json', pins)
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=VCS, VCS_TARGET_ARCH='linux64',
               SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    save(OUT / 'environment.json', env)
    results = []
    for vl, marker in ((8, 'CONTROL_COMPLETED_GLOBAL_IDLE'),
                       (9, 'CANDIDATE_REPRODUCED_NOT_ARCH_PASS')):
        case = OUT / f'vl{vl}'
        case.mkdir()
        command = [str(OLD / 'simv'), '-no_save', f'+VL={vl}']
        traced = ['/usr/bin/strace', '-ff', '-ttt', '-T', '-s', '192',
                  '-e', 'trace=process,network,openat,poll,ppoll,select,pselect6,futex,clock_nanosleep,close,fcntl',
                  '-o', str(case / 'strace'), *command]
        save(case / 'command.json', {'simulator': command, 'diagnostic': traced,
                                    'host_bound_s': 60, 'rtl_watchdog_ns': 2000})
        start = time.monotonic()
        samples = []
        expired = False
        with (case / 'run.log').open('x') as log:
            child = subprocess.Popen(traced, cwd=case, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            save(case / 'invocation.json', {'pid': child.pid, 'owner_pid': os.getpid(),
                                           'started_epoch': time.time()})
            for deadline in (1, 5, 15, 30, 55, 60):
                try:
                    child.wait(timeout=max(.001, start + deadline - time.monotonic()))
                    break
                except subprocess.TimeoutExpired:
                    samples.append({'elapsed_s': time.monotonic()-start, 'process': snapshot(child.pid),
                                    'cycles_exists': (case / 'cycles.csv').exists(),
                                    'cycles_bytes': (case / 'cycles.csv').stat().st_size if (case / 'cycles.csv').exists() else None})
            if child.poll() is None:
                expired = True
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        save(case / 'process_samples.json', samples)
        log = (case / 'run.log').read_text()
        record = {'vl': vl, 'tracer_returncode': child.returncode,
                  'host_deadline_expired': expired, 'elapsed_s': time.monotonic()-start,
                  'marker_count': log.count(marker), 'cycles_exists': (case / 'cycles.csv').exists()}
        if (case / 'cycles.csv').exists():
            rows = (case / 'cycles.csv').read_text().splitlines()
            record.update(csv_lines=len(rows), last_csv_line=rows[-1] if rows else None)
        save(case / 'result.json', record)
        results.append(record)
        print(json.dumps(record), flush=True)
        if expired or child.returncode != 0 or record['marker_count'] != 1:
            break
    unchanged = all(sha(Path(p)) == h for p, h in pins.items())
    unchanged &= all(sha(OLD / 'frozen' / p) == h for p, h in frozen.items())
    save(OUT / 'result.json', {'cases': results, 'pins_unchanged': unchanged,
                             'scope': 'Host startup diagnosis; not architectural acceptance'})
    return 0 if unchanged else 1


if __name__ == '__main__':
    raise SystemExit(main())
