#!/usr/bin/env python3
"""Run the original full cache ELF once, after fresh 6+17 acceptance on build04.

A collected successful transient service is permitted, not an active/failed
prerequisite or incomplete evidence. Preparation only without --execute.
No old receipt changes, RTL changes, reduced workload, or full regression.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import run_failed_repair_20261008_v5 as accepted
import audit_system_cache_repair as checker

base, require, ROOT = accepted.base, accepted.require, accepted.ROOT
IMAGE_DIR = ROOT / 'verification/out/failed-repair-image-20261008-04'


def service_terminal(service):
    require(service.get('MainPID') == '0' and service.get('ActiveState') == 'inactive',
            'acceptance service is active/failed or lacks terminal state')
    require(service.get('LoadState') in ('loaded', 'not-found'), 'invalid acceptance service state')
    if service['LoadState'] == 'loaded':
        require(service.get('ExecMainStatus') == '0', 'acceptance process exited unsuccessfully')
    # ExecMainStatus=0 on a missing unit is a systemd default, not exit evidence.
    return service['LoadState'] == 'not-found'


def ensure_simulator_gone(started):
    pid = started.get('pid')
    require(type(pid) is int and pid > 0, 'missing simulator PID')
    try:
        command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:
        return
    # A recycled PID belonging to another program does not invalidate a run.
    require(not command or command[0] != os.fsencode(started['image']),
            'recorded simulator is still running')


def acceptance_gate(directory, image_dir, service, runner_sha):
    directory, image_dir = directory.resolve(strict=True), image_dir.resolve(strict=True)
    require(image_dir == IMAGE_DIR.resolve(), 'only build04 may dispatch cache')
    collected = service_terminal(service)
    status_path, source_path = directory / 'status.json', directory / 'source-pins.json'
    sealed = base.pins([status_path, source_path])
    state, pins = base.read(status_path), base.read(source_path)
    require(state.get('status') == 'PASS' and state.get('total') == 23 and state.get('fresh_runs_only') is True and
            set(state.get('cases', {})) == set(accepted.prior.EXPECTED_SCOPE),
            'all original six plus seventeen neighbours must pass')
    image = image_dir / 'sim/simv'
    build_pins, _ = accepted.build_evidence(image_dir)
    require(state.get('image') == str(image) and build_pins and
            all(pins.get(p) == h for p, h in build_pins.items()), 'acceptance image/source differs')
    path = Path(accepted.__file__).resolve()
    require(runner_sha and pins.get(str(path)) == runner_sha == base.sha256(path),
            'sealed acceptance v5 runner differs')
    base.check(pins)
    pins = accepted.merge_pins(pins, build_pins, sealed)
    records = {}
    for name in accepted.prior.EXPECTED_SCOPE:
        case = directory / 'results' / name
        receipt = base.read(case / 'audit.json')
        require(receipt == state['cases'][name] and receipt.get('status') == 'PASS' and
                receipt.get('directory') == str(case), 'case is not the recorded PASS: ' + name)
        evidence = receipt.get('evidence', {})
        require(evidence and evidence.get('status', 'PASS') == 'PASS' and
                evidence.get('failures', 0) == 0, 'failed/missing independent audit: ' + name)
        origin = case
        require(receipt.get('simulation_launched') is True and
                receipt.get('reused_completed_same_image') is False and
                receipt.get('simulator_process_exit_verified') is True,
                'all23 must be fresh completed v5 runs: ' + name)
        for key in ('input_pins', 'output_pins'):
            pins = accepted.merge_pins(pins, evidence.get(key, {}))
        launch, command = base.read(origin / 'started.json'), base.read(origin / 'command.json')
        exit_path = case / 'simulation-exit.json'
        exit_record = base.read(exit_path)
        require(receipt.get('process_exit_receipt') == str(exit_path) and
                receipt.get('process_exit_receipt_sha256') == base.sha256(exit_path) and
                all(exit_record.get(k) == v for k, v in launch.items()) and
                type(exit_record.get('returncode')) is int and exit_record['returncode'] == 0 and
                exit_record.get('timeout') is False and
                exit_record.get('exit_observed_by') == 'owning worker Popen.wait' and
                exit_record.get('finished_unix', 0) >= launch.get('started_unix', float('inf')),
                'missing/mismatched zero-exit receipt: ' + name)
        require(launch.get('image') == str(image) and launch.get('image_sha256') == base.sha256(image),
                'case image differs: ' + name)
        require(launch.get('elf_sha256') == base.sha256(case / 'input.elf') ==
                base.sha256(accepted.legacy.source(name) / 'input.elf'), 'case ELF differs: ' + name)
        require(command.get('cwd') == str(origin) and command.get('timeout_s') == 1800 and
                command.get('command') == launch.get('command') ==
                accepted.legacy.simulation_command(image, origin, name), 'launch contract differs: ' + name)
        ensure_simulator_gone(launch)
        terminal = accepted.prior.completed_logs(case, name)
        require(terminal['last_cycle'] == receipt.get('last_cycle'), 'completion cycle differs: ' + name)
        pins.update(base.pins([case / 'audit.json', case / 'input.elf', exit_path, origin / 'started.json',
                              origin / 'command.json', *[case / f for f in accepted.prior.RAW_FILES
                                                       if (case / f).is_file()]]))
        records[name] = dict(status='PASS', origin=str(origin), terminal=terminal)
    base.check(pins)
    return dict(status='PASS', cases=records, count=23, image=str(image), input_pins=pins,
                service=service, service_collected=collected, no_recorded_simulator_running=True,
                independent_process_exit_receipt=True,
                exit_evidence='All23 owning-worker simulation-exit.json receipts bind zero returncode, '
                              'no timeout, original launch and audited result; normal finish rechecked. '
                              'Missing-unit ExecMainStatus defaults are not treated as proof.',
                coverage_admitted=False)


def acceptance_ready(status, service):
    require(status.get('status') not in ('FAIL', 'STOPPED', 'TIMEOUT'), 'acceptance failed')
    if service.get('ActiveState') in ('active', 'activating') and service.get('LoadState') == 'loaded':
        return False
    service_terminal(service)
    require(status.get('status') == 'PASS', 'missing/collected service without completed acceptance PASS')
    return True


def wait_acceptance(directory, unit):
    deadline = time.monotonic() + 10800
    while True:
        path = directory / 'status.json'
        status = base.read(path) if path.is_file() else {}
        observed = subprocess.run(['systemctl', '--user', 'show', unit,
            '--property=ActiveState', '--property=MainPID', '--property=ExecMainStatus',
            '--property=LoadState'], capture_output=True, text=True, timeout=10)
        service = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
        require(observed.returncode == 0 or service.get('LoadState') == 'not-found', 'service query failed')
        if acceptance_ready(status, service):
            return service
        require(time.monotonic() < deadline, 'acceptance wait budget exhausted; no restart')
        time.sleep(60)


def normal_finish(directory):
    times = []
    for name in ('console.log', 'run.vcs.log'):
        text = (directory / name).read_text()
        checker.check_log(text)
        require('$finish called from file' in text and
                'V C S   S i m u l a t i o n   R e p o r t' in text, 'cache simulation did not finish normally')
        stamps = re.findall(r'^Time:\s*(\d+)\s+fs\s*$', text, re.M)
        require(len(stamps) == 1 and int(stamps[0]) > 0, 'missing cache finish timestamp')
        times.append(int(stamps[0]))
    require(times[0] == times[1], 'cache console/run timestamps differ')
    return times[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--image-directory', type=Path, default=IMAGE_DIR)
    parser.add_argument('--acceptance', type=Path)
    parser.add_argument('--acceptance-unit')
    parser.add_argument('--acceptance-runner-sha256', help='Parent-confirmed final v5 SHA256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status='PREPARED_ONLY', case='system_gap30_cache',
            checks=1758, image_directory=str(IMAGE_DIR), prerequisite='fresh v5 all23 PASS',
            original_ELF=checker.ELF_SHA, full_regression_started=False), indent=2))
        return 0
    require(args.output is not None and args.acceptance is not None and args.acceptance_unit and
            args.acceptance_runner_sha256, 'new output, acceptance/unit and approved v5 SHA required')
    base.check_service()
    out = base.checked_output(args.output)
    out.mkdir(exist_ok=False)
    state = dict(status='WAITING_ACCEPTANCE', case='system_gap30_cache',
                 acceptance=str(args.acceptance.resolve()), full_regression_started=False)
    base.save(out / 'status.json', state)
    try:
        service = wait_acceptance(args.acceptance, args.acceptance_unit)
        gate = acceptance_gate(args.acceptance, args.image_directory, service, args.acceptance_runner_sha256)
        base.save(out / 'acceptance-gate.json', gate)
        image = args.image_directory.resolve(strict=True) / 'sim/simv'
        pins = dict(gate['input_pins'])
        pins.update(base.pins(Path(m.__file__) for m in list(sys.modules.values())
            if getattr(m, '__file__', None) and
            str(Path(m.__file__).resolve()).startswith(str(ROOT / 'verification')) and
            Path(m.__file__).is_file()))
        shutil.copyfile(checker.source() / 'input.elf', out / 'input.elf')
        require(base.sha256(out / 'input.elf') == checker.ELF_SHA, 'different original cache ELF')
        pins.update(base.pins([checker.source() / 'input.elf', out / 'input.elf', out / 'acceptance-gate.json']))
        base.check(pins)
        base.save(out / 'source-pins.json', pins)
        command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=system_gap30_cache',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
            '-cm_name', 'system_gap30_cache']
        base.save(out / 'command.json', dict(command=command, cwd=str(out), timeout_s=1800))
        state.update(status='RUNNING', image=str(image))
        base.save(out / 'status.json', state)
        with (out / 'console.log').open('w') as log:
            with subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT) as process:
                base.save(out / 'started.json', dict(pid=process.pid, image=str(image),
                    image_sha256=base.sha256(image), elf_sha256=checker.ELF_SHA))
                try:
                    code = process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    base.save(out / 'process-exit.json', dict(pid=process.pid, timed_out=True,
                                                              returncode=process.returncode))
                    raise
                base.save(out / 'process-exit.json', dict(pid=process.pid, timed_out=False, returncode=code))
                require(code == 0, 'simulator failed: ' + str(code))
        base.check(pins)
        finish = normal_finish(out)
        evidence = checker.audit(out)
        require(evidence.get('status') == 'PASS' and evidence['last_cycle'] * 1000000 <= finish,
                'cache strict audit/finish boundary failed')
        base.save(out / 'audit.json', evidence)
        state.update(status='PASS', checks=evidence['checks'], last_cycle=evidence['last_cycle'])
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
    base.save(out / 'status.json', state)
    return 0 if state['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
