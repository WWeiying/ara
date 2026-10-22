#!/usr/bin/env python3
"""Fresh, fixed 6+17 acceptance on a selected source-checked image.

Preparation summary by default; --execute requires an owning systemd service.
No build, prior-run reuse, retries, RTL edits, merging or full-suite dispatch.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

import run_failed_repair_20261008_v3 as prior

legacy, base, ROOT = prior.legacy, prior.base, prior.ROOT
require = prior.require
FOCUSED, NEIGHBOURS = prior.FOCUSED, prior.NEIGHBOURS
SCOPE = prior.EXPECTED_SCOPE
SEALS = {
    'run_failed_repair_20261008_v2.py': prior.V2_SHA,
    'run_failed_repair_20261008_v3.py': '3e3099d5b9fd99fec058c18cddd4e4731ee258cb9e9c0fafd2bc0efffd29e755',
    'audit_qbs_canonical_repair_v2.py': prior.QBS_CHECKER_SHA,
    'audit_fof_repair_v3.py': '17047054ff82c8495c6a7f480c0cc198a7543d545efa1fd294d7ecc02bdc104a',
    'build_memory_vl0_repair.py': 'a346b1e825c3af06f6b91a63dcc49808db09fb752eeaa1000076c1a9acb73c7d',
    'run_vcs_dve_checkpoint.py': 'eb339dc5caf5b6af542536ea19c3a11c982bb40839a87cc3348922eb7d07a93b',
}


def sealed_modules():
    require(FOCUSED + NEIGHBOURS == SCOPE and (len(FOCUSED), len(NEIGHBOURS)) == (6, 17)
            and len(set(SCOPE)) == 23, 'Fixed 6+17 scope changed')
    base.check({str(Path(__file__).with_name(name)): digest for name, digest in SEALS.items()})
    for name in ('audit_qbs_canonical_repair_v2', 'audit_fof_repair_v3',
                 'audit_mask_restart_repair', 'audit_memory_decode_repair'):
        importlib.import_module(name)


def merge_pins(*maps):
    pins = {}
    for mapping in maps:
        for path, digest in mapping.items():
            require(path not in pins or pins[path] == digest, 'Conflicting provenance pin: ' + path)
            pins[path] = digest
    return pins


def build_evidence(image_dir):
    """Persisted build PASS proves checked compiler completion, not a live unit.

    The sealed builder uses subprocess.run(check=True), checks the source
    manifest/config, and only then writes PASS plus the exact runtime image.
    Its historical schema has no independent compiler OS-exit receipt.
    """
    image_dir = Path(image_dir).resolve(strict=True)
    image = image_dir / 'sim/simv'
    status = base.read(image_dir / 'build-status.json')
    sources = base.read(image_dir / 'build-source-pins.json')
    images = base.read(image_dir / 'build-image.json')
    tools = base.read(image_dir / 'build-tool-pins.json')
    require(status.get('status') == 'PASS' and status.get('old_vdb_reuse') is False,
            'Completed fresh source-checked build required')
    require(sources and len(images) >= 2 and str(image) in images and
            status.get('image') == images, 'Missing/mismatched build image/source receipt')
    for name in ('build_memory_vl0_repair.py', 'run_vcs_dve_checkpoint.py'):
        require(tools.get(str(Path(__file__).with_name(name))) == SEALS[name],
                'Unreviewed build producer; cannot infer checked compiler exit')
    require(os.access(image, os.X_OK) and base.simulation_image(image) == images,
            'Runtime executable/library inventory differs')
    manifest_path = image_dir / 'sim/vcs_source_manifest.json'
    manifest = base.sources(manifest_path)
    actual = {r['path']: r['sha256'] for r in manifest['files']
              if not Path(r['path']).is_relative_to(image_dir)}
    require(actual == sources, 'Compiled source manifest differs from build source pins')
    command = base.read(image_dir / 'compile.command.json')
    require(command == dict(command=legacy.builder.compile_command(image_dir), cwd=str(ROOT),
                            timeout_s=7200), 'Build command/configuration differs')
    records = [image_dir / name for name in ('build-status.json', 'build-source-pins.json',
                'build-image.json', 'build-tool-pins.json', 'compile.command.json', 'compile.log')]
    records += [manifest_path, image_dir / 'sim/simulator.conf']
    pins = merge_pins(sources, images, tools, base.pins(records))
    base.check(pins)
    return pins, dict(image=str(image), image_sha256=images[str(image)],
        source_count=len(sources), runtime_files=len(images), build_unit=status.get('unit'),
        compiler_exit_basis='sealed builder checked subprocess exit then source/config/image PASS',
        independent_compiler_exit_receipt=False)


def build_ready(status, unit, service):
    """Classify a single service observation without treating GC as failure."""
    require(not status or status.get('unit') == unit, 'Build receipt/service identity mismatch')
    require(not status or status.get('status') in ('BUILDING', 'PASS'), 'Build failed')
    if service.get('LoadState') == 'not-found':
        require(status.get('status') == 'PASS', 'Collected/missing unit without persisted build PASS')
        return True
    if service.get('ActiveState') in ('active', 'activating'):
        return False
    require(service.get('ActiveState') == 'inactive' and service.get('MainPID') == '0' and
            service.get('ExecMainStatus') == '0' and service.get('Result') == 'success' and
            status.get('status') == 'PASS', 'Build service did not complete successfully')
    return True


def wait_build(image_dir, unit, output):
    deadline = time.monotonic() + 7200
    while True:
        path = image_dir / 'build-status.json'
        status = base.read(path) if path.is_file() else {}
        proc = subprocess.run(['systemctl', '--user', 'show', unit,
            '-p', 'LoadState', '-p', 'ActiveState', '-p', 'MainPID',
            '-p', 'ExecMainStatus', '-p', 'Result'], capture_output=True, text=True, timeout=10)
        service = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
        require(proc.returncode == 0 or service.get('LoadState') == 'not-found',
                'Unable to query build service')
        if build_ready(status, unit, service):
            # The complete source/image validation follows, even for a collected unit.
            base.save(output / 'build-service-observation.json', service)
            return
        require(time.monotonic() < deadline, 'Build wait budget exhausted; no restart')
        time.sleep(60)


def prepare_cases(output, image):
    """Materialize all 23 original ELFs and validate every launch before dispatch."""
    pins, commands = {}, {}
    for name in SCOPE:
        directory = output / 'results' / name
        directory.mkdir(parents=True, exist_ok=False)
        origin = legacy.source(name)
        for filename in ('input.elf', 'spike.trace'):
            source = origin / filename
            if filename == 'input.elf' or source.is_file():
                shutil.copyfile(source, directory / filename)
                pins.update(base.pins([source, directory / filename]))
        command = legacy.simulation_command(image, directory, name)
        require(command[0] == str(image), 'Command selected a different simulator')
        commands[name] = command
        base.save(directory / 'command.json', dict(command=command, cwd=str(directory), timeout_s=1800))
        pins.update(base.pins([directory / 'command.json']))
    base.check(pins)
    return pins, commands


def audit(directory, name):
    terminal = prior.completed_logs(directory, name)
    if name == 'qbs_canonical':
        module = importlib.import_module('audit_qbs_canonical_repair_v2')
        evidence = module.audit(directory, output=directory / 'qbs-canonical-audit-v2')
    elif name == 'vgap112_sv39_fof':
        evidence = importlib.import_module('audit_fof_repair_v3').audit(directory)
    else:
        evidence = legacy.audit(directory, name)
    require(evidence.get('status', 'PASS') == 'PASS', 'Case auditor did not pass')
    return evidence, terminal


def run_case(name, output, image, pins, command):
    directory = output / 'results' / name
    started = time.monotonic()
    result = dict(status='RUNNING', directory=str(directory), simulation_launched=False,
                  reused_completed_same_image=False, coverage_admitted=False)
    try:
        base.check(pins)
        require(all(p.name in ('input.elf', 'spike.trace', 'command.json') for p in directory.iterdir()),
                'Case has prior attempt artifacts; refuse automatic retry')
        require(command == legacy.simulation_command(image, directory, name), 'Preflight command drift')
        launch = dict(image=str(image), image_sha256=base.sha256(image),
            elf_sha256=base.sha256(directory / 'input.elf'), command=command,
            cwd=str(directory), timeout_s=1800, worker_pid=os.getpid())
        with (directory / 'console.log').open('x') as log:
            # Still owned by this systemd cgroup; private pgid bounds timeout cleanup.
            with subprocess.Popen(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True) as proc:
                result['simulation_launched'] = True
                launch.update(pid=proc.pid, started_unix=time.time())
                timed_out = False
                try:
                    base.save(directory / 'started.json', launch)
                    try:
                        code = proc.wait(timeout=1800)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        os.killpg(proc.pid, signal.SIGKILL)
                        code = proc.wait()
                except BaseException:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    raise
                finally:
                    base.save(directory / 'simulation-exit.json', dict(launch,
                        returncode=proc.returncode, timeout=timed_out, finished_unix=time.time(),
                        exit_observed_by='owning worker Popen.wait', audit_started=False))
        require(not timed_out, 'Simulator timeout; no retry')
        require(type(code) is int and code == 0, 'Simulator nonzero exit: ' + str(code))
        base.check(pins)
        evidence, terminal = audit(directory, name)
        base.check(pins)
        result.update(status='PASS', evidence=evidence, terminal=terminal,
            last_cycle=terminal['last_cycle'], simulator_process_exit_verified=True,
            process_exit_receipt=str(directory / 'simulation-exit.json'),
            process_exit_receipt_sha256=base.sha256(directory / 'simulation-exit.json'))
    except Exception as error:
        result.update(status='FAIL', reason=f'{type(error).__name__}: {error}')
    result['elapsed_s'] = round(time.monotonic() - started, 3)
    base.save(directory / 'audit.json', result)
    return name, result


def dispatch(output, image, pins, commands, jobs):
    state = dict(status='RUNNING', total=23, image=str(image), fresh_runs_only=True,
        old_vdb_reuse=False, full_regression_started=False,
        cases={name: dict(status='QUEUED') for name in SCOPE})
    def save():
        base.save(output / 'status.json', state)
    for gate in (FOCUSED, NEIGHBOURS):
        state['phase'] = 'original failures' if gate == FOCUSED else 'bounded neighbours'
        failed = False
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            pending, running = iter(gate), {}
            def submit():
                name = next(pending, None)
                if name is not None:
                    state['cases'][name] = dict(status='RUNNING')
                    running[pool.submit(run_case, name, output, image, pins, commands[name])] = name
            for _ in range(min(jobs, len(gate))):
                submit()
            save()
            while running:
                # Drain the complete ready set before any replacement dispatch.
                future = next(as_completed(running))
                ready = [f for f in running if f is future or f.done()]
                for future in ready:
                    name = running.pop(future)
                    try:
                        returned, result = future.result()
                        require(returned == name, 'Worker case identity differs')
                    except Exception as error:
                        result = dict(status='FAIL', controller_error=f'{type(error).__name__}: {error}')
                        base.save(output / 'results' / name / 'audit.json', result)
                    state['cases'][name] = result
                    failed |= result['status'] != 'PASS'
                if not failed:
                    for _ in ready:
                        submit()
                save()
        if failed:
            state.update(status='STOPPED', phase='failed gate; no further dispatch or retry')
            save()
            return 1
    base.check(pins)
    state.update(status='PASS', phase='23 fresh cases complete; paused before any full suite')
    save()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--image-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-build-unit')
    parser.add_argument('--jobs', type=int, choices=range(1, 6), default=5)
    args = parser.parse_args(argv)
    sealed_modules()
    image_dir = args.image_directory.resolve()
    output = base.checked_output(args.output)
    require(not output.exists() and not output.is_relative_to(image_dir) and
            not image_dir.is_relative_to(output), 'Fresh separate output required')
    if not args.execute:
        print(json.dumps(dict(status='PREPARED_ONLY', image_directory=str(image_dir), output=str(output),
            focused=FOCUSED, neighbours=NEIGHBOURS, total=23, fresh_runs_only=True,
            qbs_checker='audit_qbs_canonical_repair_v2', fof_checker='audit_fof_repair_v3',
            simulation_launched=False, full_regression_started=False), indent=2))
        return 0
    base.check_service()
    active = False
    try:
        output.mkdir(exist_ok=False)
        active = True
        base.save(output / 'status.json', dict(status='WAITING_BUILD', total=23, fresh_runs_only=True))
        if args.wait_build_unit:
            wait_build(image_dir, args.wait_build_unit, output)
        build_pins, provenance = build_evidence(image_dir)
        image = image_dir / 'sim/simv'
        input_pins, commands = prepare_cases(output, image)
        local = [Path(__file__), legacy.READELF, legacy.AXPY / 'cycle_comparison.json',
                 ROOT / 'verification/coverage/gap71_canonical_qbs_positive779_probe.tcl',
                 ROOT / 'verification/coverage/mask_compare_restart_known786_probe.tcl']
        local += [Path(m.__file__) for m in list(sys.modules.values()) if getattr(m, '__file__', None)
                  and Path(m.__file__).is_file() and Path(m.__file__).resolve().is_relative_to(ROOT / 'verification')]
        pins = merge_pins(build_pins, input_pins, base.pins(local))
        base.check(pins)
        base.save(output / 'source-pins.json', pins)
        base.save(output / 'build-provenance.json', provenance)
        base.save(output / 'launch-preflight.json', dict(status='READY', total=23,
            commands=commands, fresh_runs_only=True, all_original_ELFs=True))
        code = dispatch(output, image, pins, commands, args.jobs)
        # Recheck the complete .so inventory, not just already-known filenames.
        build_evidence(image_dir)
        return code
    except Exception as error:
        if active:
            path = output / 'status.json'
            state = base.read(path) if path.is_file() else {}
            state.update(status='STOPPED', controller_error=f'{type(error).__name__}: {error}')
            base.save(path, state)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
