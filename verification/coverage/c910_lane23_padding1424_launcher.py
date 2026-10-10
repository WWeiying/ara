#!/usr/bin/env python3
"""Parent-reviewed one-shot systemd worker for the frozen local1424 gates."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import c910_lane23_padding1424_local_v3 as core

life, need = core.life, core.need
tools = core.ptw.primitive.old.frozen.tools
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_c910_lane23_padding1424_launcher.py')


def approved(seal, reviewed):
    need(isinstance(seal, str) and len(seal) == 64 and seal == reviewed,
         'Exact explicit parent-reviewed config seal required')


def host_tools():
    return [tools.seal_file(p) for p in
            (Path('/usr/bin/systemd-run'), Path('/usr/bin/systemctl'), Path(sys.executable).resolve())]


def contract(out):
    paths = os.environ.get('PYTHONPATH', '').split(os.pathsep)
    need(paths and all(p and Path(p).is_absolute() and Path(p).is_dir() for p in paths),
         'Explicit absolute child PYTHONPATH')
    return dict(schema='C1424_SYSTEMD_ONE_SHOT_V1', timeout_seconds=900, automatic_retry=False,
        environment_seal='C1424_CONFIG_SEAL', uid=os.getuid(),
        unit='c9101424-local-' + core.hashlib.sha256(str(out).encode()).hexdigest()[:20],
        pythonpath=os.pathsep.join(paths), host_tools=host_tools())


def prepare(out):
    receipt = core.prepare(out)
    c = json.loads((out / 'config.json').read_bytes())
    c['launch_contract'] = contract(out)
    for p in (SCRIPT, TEST, Path(core.__file__).resolve(), core.TEST):
        c['pins'][str(p)] = life.digest(p)
    for row in c['launch_contract']['host_tools']:
        c['pins'][row['path']] = row['sha256']
    # Keep the core prepare receipt/config; only this still-unpublished fresh packet is extended.
    (out / 'config.json').rename(out / 'core-prepared-config.json')
    life.save(out / 'core-prepare-receipt.json', receipt)
    for p in (out / 'core-prepared-config.json', out / 'core-prepare-receipt.json'):
        c['pins'][str(p)] = life.digest(p)
    life.save(out / 'config.json', c)
    return dict(output=str(out), seal=life.digest(out / 'config.json'), EDA_started=False,
                timeout_seconds=900, status='FROZEN_PREPARED_NATIVE_HOLD_PARENT_REVIEW_REQUIRED')


def check(out, seal):
    c = core.check(out, seal)
    need(c['launch_contract'] == contract(out), 'Exact systemd/host-tools/import-path contract')
    tools.revalidate(c['identity'])
    for p in (SCRIPT, TEST, Path(core.__file__).resolve(), core.TEST):
        need(c['pins'].get(str(p)) == life.digest(p), 'Launcher/test/core required pin')
    return c


def service_command(c, out, seal):
    h = c['launch_contract']
    systemd, _, python = [row['path'] for row in h['host_tools']]
    return [systemd, '--user', '--unit=' + h['unit'], '--collect', '--working-directory=' + str(out),
        '--property=Type=exec', '--property=KillMode=control-group', '--property=RuntimeMaxSec=900',
        '--property=TimeoutStopSec=10', '--setenv=C1424_CONFIG_SEAL=' + seal,
        '--setenv=PYTHONPATH=' + h['pythonpath'], python, '-B', str(SCRIPT), 'worker',
        '--output', str(out), '--seal', seal, '--parent-reviewed-seal', seal]


def launch(out, seal, reviewed):
    approved(seal, reviewed)
    c = check(out, seal)
    need(not any((out / n).exists() for n in ('service-request.json', 'execution.json', 'terminal.json')),
         'One shot only; no retries')
    cmd = service_command(c, out, seal)
    life.save(out / 'service-request.json', dict(config_seal=seal, reviewed_seal=reviewed,
        command=cmd, unit=c['launch_contract']['unit'], uid=os.getuid(), timeout_seconds=900))
    result = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=30)
    life.save(out / 'service-launch-receipt.json', dict(returncode=result.returncode,
        stdout=result.stdout, stderr=result.stderr, command=cmd))
    need(type(result.returncode) is int and result.returncode == 0, 'Actual systemd worker submission failed')
    return dict(status='PARENT_APPROVED_SYSTEMD_WORKER_SUBMITTED_NOT_QUALIFIED', unit=c['launch_contract']['unit'])


def cgroup_gate(text, h):
    lines = text.splitlines()
    need(lines and any(line.endswith('/' + h['unit'] + '.service') and
         '/user@%d.service/' % h['uid'] in line for line in lines), 'Worker must belong to exact user systemd service')
    return text


def proc_cgroup(pid):
    return Path('/proc/%d/cgroup' % pid).read_text()


def live_gate(row, c, execution):
    need(type(row['pid']) is int and row['pid'] > 0 and row['exe'] == c['identity']['executable'] and
         row['cwd'] == c['output'] and row['cgroup'] == execution['worker_cgroup'], 'Actual DVE exe/cwd/cgroup')
    cgroup_gate(row['cgroup'], c['launch_contract'])
    proof = row['process_identity']
    need(proof['executable_verified'] is True and proof['pid'] == row['pid'] and
         proof['executable'] == row['exe'] and proof['launch_pid'] == execution['launch_pid'] and
         proof['launch_starttime'] == execution['launch_starttime'] and
         type(proof['starttime']) is int and proof['starttime'] >= proof['launch_starttime'],
         'Measured sealed native child ancestry/starttime')


def observe(c, out, proc, start, execution):
    live = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if (path / 'exe').resolve() != Path(c['identity']['executable']) or (path / 'cwd').resolve() != out:
                continue
            pid = int(path.name)
            row = dict(pid=pid, exe=str((path / 'exe').resolve()), cwd=str((path / 'cwd').resolve()),
                cgroup=proc_cgroup(pid), process_identity=tools.verify_live_executable(pid, c['identity'], proc.pid, start))
            live_gate(row, c, execution)
            live.append(row)
        except (OSError, ValueError):
            continue
    return live


def verify(out, seal):
    c = check(out, seal)
    need(not (out / 'worker-error.json').exists(), 'Recorded worker failure is not qualification')
    e = json.loads((out / 'execution.json').read_bytes())
    request = json.loads((out / 'service-request.json').read_bytes())
    submitted = json.loads((out / 'service-launch-receipt.json').read_bytes())
    need(request == dict(config_seal=seal, reviewed_seal=seal, command=service_command(c, out, seal),
         unit=c['launch_contract']['unit'], uid=c['launch_contract']['uid'], timeout_seconds=900), 'Exact parent/systemd request')
    need(type(submitted['returncode']) is int and submitted['returncode'] == 0 and
         submitted['command'] == request['command'], 'Actual service submit0')
    need(e['service_unit'] == request['unit'] and type(e['worker_pid']) is int and e['worker_pid'] > 0,
         'Persistent worker identity')
    cgroup_gate(e['worker_cgroup'], c['launch_contract'])
    live = json.loads((out / 'live-identity.json').read_bytes())
    need(len(live) == 1, 'One actual DVE child')
    live_gate(live[0], c, e)
    result = core.verify(out, seal)
    extra = ['service-request.json', 'service-launch-receipt.json', 'launcher.log', 'worker.log']
    result['pins'] = life.merge_pins(result['pins'], {str(out / n): life.digest(out / n) for n in extra})
    result.update(service_unit=request['unit'], native_cgroup_verified=True, parent_reviewed_seal=seal,
                  terminal_returncode=0, timeout_seconds=900)
    life.check(result['pins'])
    dest = out / 'capture-result.json'
    if dest.exists():
        need(json.loads(dest.read_bytes()) == result, 'Existing sealed qualification differs')
    else:
        life.save(dest, result)
    return result


def worker(out, seal, reviewed):
    approved(seal, reviewed)
    deadline = time.monotonic() + 900
    c = check(out, seal)
    need(os.environ.get('C1424_CONFIG_SEAL') == seal, 'Exact C1424 environment seal')
    group = cgroup_gate(proc_cgroup(os.getpid()), c['launch_contract'])
    request = json.loads((out / 'service-request.json').read_bytes())
    need(request['command'] == service_command(c, out, seal) and request['reviewed_seal'] == seal,
         'Exact independent parent authorization')
    need(not (out / 'execution.json').exists(), 'One native attempt only')
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), C1424_CONFIG_SEAL=seal,
               PYTHONPATH=c['launch_contract']['pythonpath'])
    cmd = core.ptw.command(c, out)
    execution = dict(command=cmd, cwd=str(out), config_seal=seal, timeout_seconds=900,
        service_unit=c['launch_contract']['unit'], worker_pid=os.getpid(), worker_cgroup=group)
    proc, live, timeout, rc = None, [], False, -1
    try:
        with (out / 'launcher.log').open('x') as log, (out / 'worker.log').open('x') as worker_log:
            worker_log.write('Persistent systemd worker owns and waits for sealed DVE child\n')
            worker_log.flush()
            proc = subprocess.Popen(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(proc.pid)['starttime']
            execution.update(launch_pid=proc.pid, launch_starttime=start)
            life.save(out / 'execution.json', execution)
            probe_deadline = min(deadline - 10, time.monotonic() + 60)
            while time.monotonic() < probe_deadline:
                live = observe(c, out, proc, start, execution)
                if live or proc.poll() is not None:
                    break
                time.sleep(0.5)
            life.save(out / 'live-identity.json', live)
            need(len(live) == 1, 'Actual sealed native child not found in worker cgroup')
            try:
                proc.wait(timeout=max(0, deadline - 10 - time.monotonic()))
            except subprocess.TimeoutExpired:
                timeout = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
            rc = proc.returncode
    except Exception as error:
        life.save(out / 'worker-error.json', dict(error=str(error), EDA_started=proc is not None))
        if proc is not None:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            rc = proc.returncode
        raise
    finally:
        life.save(out / 'terminal.json', dict(returncode=rc, timeout=timeout, actual_dve=live,
                  service_unit=c['launch_contract']['unit'], worker_cgroup=group))
    # The submitter may still be writing its real returncode receipt.
    receipt_deadline = time.monotonic() + 5
    while not (out / 'service-launch-receipt.json').exists() and time.monotonic() < receipt_deadline:
        time.sleep(0.1)
    return verify(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'launch-reviewed', 'worker', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--parent-reviewed-seal')
    a = p.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.seal is None and a.parent_reviewed_seal is None, 'Prepare cannot authorize launch')
        result = prepare(out)
    elif a.mode == 'launch-reviewed':
        result = launch(out, a.seal, a.parent_reviewed_seal)
    elif a.mode == 'worker':
        result = worker(out, a.seal, a.parent_reviewed_seal)
    elif a.mode == 'check':
        check(out, a.seal)
        result = dict(status='CHECK_PASS_NO_EDA')
    else:
        result = verify(out, a.seal)
    print(json.dumps(result, indent=2), flush=True)
