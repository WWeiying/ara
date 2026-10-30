#!/usr/bin/env python3
"""Pidfd-only four-tail barrier, then checked combine and two direct-owned H/S/B services.

Never edits a prerequisite. --inspect-only validates identities/pins without waiting
or creating downstream services. Normal execution claims the launch receipt once;
failure retains that claim and requires an explicitly reviewed successor to retry.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import select
import selectors
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split.scope import HERE, PARENT, ROOT
from verification.akv.quantized_kv.tail_split import threeway
from verification.akv.quantized_kv.tail_split.combine import checked_combined

s, Execution = threeway.s, threeway.Execution


def launch_entries(receipt):
    s.require(receipt.get('state') == 'FOUR_ACTUAL_SIMULATORS_CONFIRMED_NO_FURTHER_POLLS',
              'Not the accepted actual-owner launch receipt')
    rows = receipt.get('entries', [])
    s.require(len(rows) == 4, 'Exactly four owners required')
    keys, pids, units, outputs = set(), set(), set(), set()
    for row in rows:
        key = row.get('kind'), row.get('visible')
        s.require(key in {(k, v) for k in ('q4', 'q8') for v in (5, 33)} and
                  type(row['visible']) is int and key not in keys, 'Duplicate/unknown scope')
        s.require(type(row.get('worker_pid')) is int and row['worker_pid'] > 1 and
                  type(row.get('simulator_pid')) is int and row['simulator_pid'] > 1 and
                  row['worker_pid'] not in pids, 'Invalid/duplicate PID')
        s.require(re.fullmatch(r'[a-zA-Z0-9_-]+\.service', row.get('unit', '')) is not None and
                  row['unit'] not in units, 'Invalid/duplicate service')
        output = Path(row['output'])
        s.require(output.is_absolute() and output.resolve() == output and str(output) not in outputs,
                  'Noncanonical/duplicate output')
        argv = row['argv']
        s.require(argv.count('/usr/bin/python3') == 1, 'Ambiguous worker command')
        worker = argv[argv.index('/usr/bin/python3'):]
        s.require(len(worker) == 11 and worker[:3] == ['/usr/bin/python3', '-B', str(HERE / 'run.py')]
                  and worker[3::2] == ['--build', '--prerequisite', '--output', '--timeout'] and
                  worker[8] == str(output) and worker[10] == '7200', 'Unexpected worker argv')
        s.require(row.get('confirmation') == 'ACTUAL_SIMV_PROCESS_CONFIRMED_ONCE', 'Missing actual launch proof')
        actual = row['actual_cmdline']
        s.require(actual.count('+PRELOAD=' + str(Path(worker[4]) / 'tail_attention.elf')) == 1 and
                  actual.count('+QBS_PERF') == 1, 'Split ELF/trace association differs')
        keys.add(key); pids.add(row['worker_pid']); units.add(row['unit']); outputs.add(str(output))
    return rows


def worker_argv(row):
    return row['argv'][row['argv'].index('/usr/bin/python3'):]


def status_identity(row, status, terminal=False):
    argv = worker_argv(row)
    wanted = dict(pid=row['worker_pid'], build=argv[4], prerequisite=argv[6],
                  kind=row['kind'] + '_0', visible=row['visible'],
                  simulator_pid=row['simulator_pid'], simv=row['actual_cmdline'][0],
                  elf=str(Path(argv[4]) / 'tail_attention.elf'))
    s.require(all(type(status.get(k)) is type(v) and status[k] == v for k, v in wanted.items()),
              'Owner status identity differs')
    if terminal:
        s.require(status.get('state') == 'PASS' and status.get('child_pid') is None,
                  'Owner exited without terminal PASS')


def terminal_pass(row):
    run = Path(row['output'])
    status_identity(row, s.read_json(run / 'status.json'), terminal=True)
    result = s.read_json(run / 'result.json')
    s.require(result.get('state') == 'PASS' and result.get('post_pins_match') is True and
              result.get('independent_protocol_checked') is True and
              type(result.get('simulator_exit_code')) is int and result['simulator_exit_code'] == 0 and
              result.get('elf_sha256') == row['elf_sha256'] and
              result.get('source_pins_sha256') == s.digest(run / 'source-pins.json'),
              'Terminal split receipt is not accepted')


def systemctl(*args):
    return subprocess.run(['/usr/bin/systemctl', '--user', *args], check=True,
                          text=True, capture_output=True, timeout=30).stdout.strip()


def process_identity(pid, expected_argv, unit):
    proc = Path('/proc') / str(pid)
    before = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    argv = [x.decode() for x in (proc / 'cmdline').read_bytes().split(b'\0') if x]
    cwd = (proc / 'cwd').resolve(strict=True)
    group = (proc / 'cgroup').read_text()
    after = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    s.require(argv == expected_argv and cwd == ROOT and before == after and
              any(line.split(':', 2)[-1].rstrip('/').endswith('/' + unit) for line in group.splitlines()),
              'PID is not the expected direct-owned worker/script/cwd')
    return dict(pid=pid, start_ticks=int(before), argv=argv, cwd=str(cwd), unit=unit)


def attach(row):
    """Open the kernel identity before inspecting /proc; never wait on a bare PID."""
    status_identity(row, s.read_json(Path(row['output']) / 'status.json'))
    try:
        fd = os.pidfd_open(row['worker_pid'])
    except ProcessLookupError:
        terminal_pass(row)
        return None, dict(pid=row['worker_pid'], state='ALREADY_TERMINAL_PASS')
    try:
        if select.select([fd], [], [], 0)[0]:
            terminal_pass(row)
            os.close(fd)
            return None, dict(pid=row['worker_pid'], state='PIDFD_ALREADY_EXITED_PASS')
        try:
            identity = process_identity(row['worker_pid'], worker_argv(row), row['unit'])
            main = int(systemctl('show', row['unit'], '-p', 'MainPID', '--value'))
            if main != row['worker_pid']:
                s.require(bool(select.select([fd], [], [], 0)[0]), 'Service MainPID differs')
                terminal_pass(row)
        except (FileNotFoundError, ValueError):
            s.require(bool(select.select([fd], [], [], 0)[0]), 'Owner disappeared without pidfd exit')
            terminal_pass(row)
            identity = dict(pid=row['worker_pid'], state='EXIT_DURING_IDENTITY_PASS')
        return fd, identity
    except BaseException:
        os.close(fd)
        raise


def wait_all(handles, timeout, done):
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for fd, row in handles:
            selector.register(fd, selectors.EVENT_READ, row)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            s.require(remaining > 0, 'Owner wait exceeded bound')
            events = selector.select(remaining)
            if not events:
                raise TimeoutError('Owner pidfd wait exceeded bound')
            for key, _mask in events:
                terminal_pass(key.data)
                selector.unregister(key.fd)
                done(key.data)


def prepare_inputs(args, rows):
    launch = args.launch.resolve(strict=True)
    receipt = s.read_json(launch)
    s.require(rows == launch_entries(receipt), 'Launch mapping changed during owner attachment')
    pins = dict(receipt['source_sha256'])
    s.merge_pins(pins, s.hashes([launch]))
    for row in rows:
        path = Path(row['output']) / 'source-pins.json'
        # Written once before RUNNING. Do not pin growing status/log/result here.
        s.merge_pins(pins, s.read_json(path))
        s.merge_pins(pins, s.hashes([path]))
    targets = []
    for kind in ('q4', 'q8'):
        build = getattr(args, kind + '_build').resolve(strict=True)
        prior = getattr(args, kind + '_prerequisite').resolve(strict=True)
        report, inherited = threeway.checked_build(build)
        s.require(report['kind'] == kind + '_0', 'Wrong target build profile')
        old, extra, saved, text, _unused = threeway.terminal_inputs(
            prior, threeway.checked_strided_build, PARENT / 'run_strided_attention.py')
        s.require(old['kind'] == report['kind'] and old['accepted_image_pins'] == report['accepted_image_pins'] and
                  Path(report['predecessor_strided_build']) == Path(s.read_json(prior / 'status.json')['build']),
                  'Target strided prerequisite/image differs')
        capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
            'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block/kqv_out-0.bin'
        raw = threeway.check_strided(text, int(kind == 'q4'), capture.read_bytes(),
                                     (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
        s.require(all(saved.get(k) == v for k, v in raw.items()
                      if k not in ('state', 'independent_protocol_checked')), 'Strided raw receipt differs')
        s.merge_pins(pins, inherited); s.merge_pins(pins, extra)
        s.merge_pins(pins, report['accepted_image_pins'])
        targets.append(dict(kind=kind, build=str(build), prerequisite=str(prior), report=report))
    s.require(targets[0]['report']['accepted_image_pins'] == targets[1]['report']['accepted_image_pins'],
              'Target images differ')
    own = [Path(__file__), HERE / 'test_coordinate.py', Path(sys.executable).resolve(),
           Path('/usr/bin/python3').resolve(), Path('/usr/bin/systemctl').resolve(),
           Path('/usr/bin/systemd-run').resolve(), *s.script_files()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    s.verify_pins(pins)
    return pins, targets


def downstream_args(target, combined, output):
    return ['/usr/bin/python3', '-B', str(HERE / 'threeway.py'), '--build', target['build'],
            '--prerequisite', target['prerequisite'], '--tail-combined', str(combined),
            '--output', str(output), '--timeout', '10800']


def start_services(owner, targets, combined, out, unit_prefix, verify, attempted):
    plans = []
    for target in targets:
        kind = target['kind']
        unit = unit_prefix + '-' + kind + '.service'
        output, log = out / ('threeway-' + kind), out / ('threeway-' + kind + '.service.log')
        s.require(not output.exists() and not log.exists(), 'Downstream output already exists')
        probe = subprocess.run(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'LoadState', '--value'],
                               capture_output=True, text=True, timeout=30)
        s.require(probe.stdout.strip() == 'not-found', 'Downstream service already exists')
        worker = downstream_args(target, combined, output)
        command = ['/usr/bin/systemd-run', '--user', '--unit=' + unit, '--service-type=exec',
                   '--property=WorkingDirectory=' + str(ROOT), '--property=KillMode=control-group',
                   '--property=TimeoutStopSec=30', '--property=RuntimeMaxSec=14400',
                   '--property=StandardOutput=append:' + str(log), '--property=StandardError=append:' + str(log),
                   *worker]
        plans.append(dict(unit=unit, worker=worker, command=command, output=str(output), log=str(log)))
    s.atomic_json(out / 'downstream-plan.json', plans)
    for plan in plans:
        verify()
        # Record before systemd-run: a timed-out launcher may already have created the unit.
        attempted.append(plan['unit'])
        owner.execute(plan['command'], out / (plan['unit'] + '.launch.log'), 60, 'STARTING_DOWNSTREAM')
        pid = int(systemctl('show', plan['unit'], '-p', 'MainPID', '--value'))
        s.require(pid > 1, 'Downstream did not retain a direct service owner')
        plan['owner'] = process_identity(pid, plan['worker'], plan['unit'])
        s.atomic_json(out / 'downstream-plan.json', plans)
    verify()
    return plans


def run(args):
    s.require(1 <= args.wait_timeout <= 10800 and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', args.unit_prefix),
              'Invalid wait bound/unit prefix')
    out = args.output.resolve()
    inputs = [args.launch.resolve(strict=True)] + [getattr(args, k + suffix).resolve(strict=True)
              for k in ('q4', 'q8') for suffix in ('_build', '_prerequisite')]
    rows = launch_entries(s.read_json(inputs[0]))
    s.require(not any(out.is_relative_to(p) or p.is_relative_to(out)
                      for p in inputs + [Path(r['output']) for r in rows]), 'Independent output required')
    out.mkdir(parents=True, exist_ok=False)
    owner = Execution(out)
    owner.state.update(launch=str(inputs[0]), downstream=[], owner_observations=[])
    handles, attempted = [], []
    try:
        for row in rows:
            fd, identity = attach(row)
            if fd is not None:
                handles.append((fd, row))
            owner.state['owner_observations'].append(identity)
        pins, targets = prepare_inputs(args, rows)
        owner.state.update(unit_prefix=args.unit_prefix, targets=[dict(kind=t['kind'], build=t['build'],
                           prerequisite=t['prerequisite'], elf=t['report']['elf'],
                           elf_sha256=t['report']['elf_sha256']) for t in targets])
        s.atomic_json(out / 'pre-wait-pins.json', pins)
        receipt_sha = s.digest(out / 'pre-wait-pins.json')

        def verify():
            s.require(s.digest(out / 'pre-wait-pins.json') == receipt_sha, 'Pre-wait receipt drift')
            s.verify_pins(pins)

        verify()
        if args.inspect_only:
            owner.state['state'] = 'INSPECTED_NOT_WAITED_NOT_LAUNCHED'
            s.atomic_json(out / 'result.json', dict(state=owner.state['state'], source_pins_sha256=receipt_sha))
            return
        claim = HERE / 'out' / ('coordinate-claim-' + s.digest(inputs[0]) + '.json')
        with claim.open('x') as file:
            json.dump(dict(owner_pid=os.getpid(), output=str(out), launch=str(inputs[0])), file)
        s.merge_pins(pins, s.hashes([claim]))
        owner.state.update(state='WAITING_OWNERS', wait_timeout=args.wait_timeout)
        owner.save()
        print('WAITING_OWNERS', os.getpid(), [r['worker_pid'] for _fd, r in handles], flush=True)

        def completed(row):
            print('OWNER_EXIT_PASS', row['worker_pid'], row['output'], flush=True)

        wait_all(handles, args.wait_timeout, completed)
        verify()
        for row in rows:
            terminal_pass(row)
        combined = out / 'combined'
        owner.execute(['/usr/bin/python3', '-B', HERE / 'combine.py', '--runs',
                       *(r['output'] for r in rows), '--output', combined], out / 'combine.log', 1800, 'COMBINING')
        checked_combined(combined)
        s.merge_pins(pins, s.read_json(combined / 'source-pins.json'))
        s.merge_pins(pins, s.hashes([combined / 'source-pins.json', combined / 'result.json']))
        # Both complete preflights precede either service creation.
        for target in targets:
            pre = out / ('preflight-' + target['kind'])
            owner.execute(downstream_args(target, combined, pre) + ['--preflight-only'],
                          out / ('preflight-' + target['kind'] + '.log'), 1800, 'DOWNSTREAM_PREFLIGHT')
            report = s.read_json(pre / 'result.json')
            status = s.read_json(pre / 'status.json')
            s.require(report.get('state') == status.get('state') == 'PREFLIGHT_ONLY_NOT_EXECUTED' and
                      status.get('child_pid') is None and report.get('post_pins_match') is True and
                      report.get('source_pins_sha256') == s.digest(pre / 'source-pins.json'),
                      'Downstream preflight not accepted')
            s.merge_pins(pins, s.read_json(pre / 'source-pins.json'))
            s.merge_pins(pins, s.hashes([pre / n for n in ('source-pins.json', 'result.json', 'status.json')]))
        verify()
        checked_combined(combined)
        s.atomic_json(out / 'source-pins.json', pins)
        plans = start_services(owner, targets, combined, out, args.unit_prefix, verify, attempted)
        owner.state.update(state='DOWNSTREAM_SERVICES_STARTED', downstream=plans)
        s.atomic_json(out / 'result.json', dict(state='DOWNSTREAM_SERVICES_STARTED',
                      functional_result='NOT_CLAIMED', simulator_confirmation='NOT_YET_OBSERVED',
                      combined=str(combined), downstream=plans, post_pins_match=True,
                      source_pins_sha256=s.digest(out / 'source-pins.json')))
    except BaseException as exc:
        owner.state.update(state='STOPPED_NO_DOWNSTREAM_ACCEPTANCE', error=repr(exc))
        if attempted:
            cleanup = subprocess.run(['/usr/bin/systemctl', '--user', 'stop', *attempted],
                                     capture_output=True, text=True, timeout=120)
            owner.state['cleanup'] = dict(returncode=cleanup.returncode, stdout=cleanup.stdout, stderr=cleanup.stderr)
        s.atomic_json(out / 'result.json', dict(state=owner.state['state'], error=repr(exc)))
        raise
    finally:
        for fd, _row in handles:
            os.close(fd)
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--launch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unit-prefix', required=True)
    for kind, suffix in (('q4', '02'), ('q8', '03')):
        parser.add_argument('--' + kind + '-build', type=Path, default=ROOT /
            f'verification/out/akv-quantkv-threeway-attention-{kind}-build-20261024-{suffix}')
        parser.add_argument('--' + kind + '-prerequisite', type=Path, default=ROOT /
            f'verification/out/akv-quantkv-strided-attention-{kind}-20261024-01')
    parser.add_argument('--wait-timeout', type=int, default=10800)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)


if __name__ == '__main__':
    main()
