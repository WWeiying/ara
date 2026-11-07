#!/usr/bin/env python3
"""Direct service owner: qualify the image, then run the two independent ROIs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from build_soc import HERE, OUT, TEMPLATE, digest, require, save, verify


def wait_ready(directory, timeout):
    deadline = time.monotonic() + timeout
    while True:
        record = directory / 'build.json'
        if record.is_file():
            report = json.loads(record.read_text())
            require(report.get('state') in ('CURRENT_AREA_SOC_BUILT_NOT_EXECUTED',
                                           'CURRENT_AREA_SOC_COMPILE_AUDITED_NOT_EXECUTED',
                                           'BUILT_NOT_EXECUTED'),
                    'Prerequisite build failed: ' + str(directory))
            return
        status = directory / 'status.json'
        if status.is_file():
            value = json.loads(status.read_text()).get('state')
            require(value not in ('FAIL', 'STOPPED', 'ERROR', 'TIMEOUT'), 'Build terminal failure: ' + str(directory))
        require(time.monotonic() < deadline, 'Build wait expired: ' + str(directory))
        time.sleep(5)


def prepare_smoke(directory):
    directory.mkdir()
    original = TEMPLATE / 'inputs/rv64uv-ara-vadd'
    inherited = json.loads((TEMPLATE / 'source-pins.json').read_text())
    require(inherited.get(str(original)) == digest(original), 'Smoke executable is not accepted/pinned')
    target = directory / 'smoke.elf'
    target.write_bytes(original.read_bytes())
    pins = {str(f): digest(f) for f in (original, TEMPLATE / 'source-pins.json', target)}
    save(directory / 'source-pins.json', pins)
    save(directory / 'build.json', dict(state='BUILT_NOT_EXECUTED', elf=str(target),
        elf_sha256=digest(target), source_pins_sha256=digest(directory / 'source-pins.json'),
        artifacts={}, historical_isa_program=True, performance_measured=False))


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--soc-build', type=Path, required=True)
    p.add_argument('--q6-build', type=Path, required=True)
    p.add_argument('--f16-build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--smoke-run', type=Path)
    p.add_argument('--wait-seconds', type=int, default=7200)
    a = p.parse_args()
    out = a.output.resolve()
    require(not out.exists() and out.is_relative_to(OUT.resolve()), 'Fresh campaign output required')
    out.mkdir(parents=True)
    state = dict(state='WAITING_FOR_SEALED_BUILDS', owner_pid=os.getpid(), child_pids={},
                 started=datetime.now(timezone.utc).isoformat(), completed=[])
    statusfile = out / 'status.json'
    save(statusfile, state)
    children = {}

    def run(kind, build):
        command = [sys.executable, '-B', str(HERE / 'run_case.py'), '--soc-build', str(a.soc_build.resolve()),
                   '--build', str(build), '--kind', kind, '--output', str(out / kind), '--timeout', '10800']
        if kind == 'f16':
            command += ['--checker-name', 'check_successor.py']
        save(out / (kind + '.command.json'), dict(argv=command))
        with (out / (kind + '.worker.log')).open('x') as stream:
            child = subprocess.Popen(command, cwd=HERE, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            children[kind] = child
            # Each child publishes its own authoritative PID/state; the parent
            # avoids concurrent writes to the aggregate status inventory.
            rc = child.wait()
        require(rc == 0, kind + ' worker failed; see its original result/log')
        result = json.loads((out / kind / 'result.json').read_text())
        require(result['state'] == 'PASS', kind + ' did not pass')
        return result

    try:
        for path in (a.soc_build, a.q6_build, a.f16_build):
            wait_ready(path.resolve(), a.wait_seconds)
        pins = {str(f): digest(f) for f in (Path(__file__), HERE / 'run_case.py', HERE / 'build_soc.py')}
        save(out / 'source-pins.json', pins)
        verify(pins)
        if a.smoke_run is not None:
            directory = a.smoke_run.resolve(strict=True)
            prior = json.loads((directory / 'result.json').read_text())
            soc = json.loads((a.soc_build / 'build.json').read_text())
            require(prior.get('state') == 'PASS' and prior.get('kind') == 'smoke' and
                    prior.get('independent_protocol_checked') is True and prior.get('post_pins_match') is True and
                    prior['image_sha256'] == digest(soc['simv']) and
                    prior['source_pins_sha256'] == digest(directory / 'source-pins.json'),
                    'No same-image checked smoke')
            verify(json.loads((directory / 'source-pins.json').read_text()))
            verify(prior['artifacts'])
            state['accepted_smoke'] = str(directory)
        else:
            smoke = out / 'smoke-build'
            prepare_smoke(smoke)
            state['state'] = 'RVV_IMAGE_SMOKE'
            save(statusfile, state)
            run('smoke', smoke)
        state.update(state='RUNNING_TWO_PROFILES', completed=['smoke'])
        save(statusfile, state)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {kind: pool.submit(run, kind, path.resolve())
                       for kind, path in (('q6', a.q6_build), ('f16', a.f16_build))}
            results = {}
            for kind, future in futures.items():
                results[kind] = future.result()
                state['completed'].append(kind)
                save(statusfile, state)
        verify(pins)
        save(out / 'result.json', dict(state='PROFILE_RUNS_CHECKED', results=results,
             performance_attribution_complete=False, note='Requires final cycle/source attribution audit'))
        state.update(state='PROFILE_RUNS_CHECKED', finished=datetime.now(timezone.utc).isoformat())
        save(statusfile, state)
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc), finished=datetime.now(timezone.utc).isoformat())
        save(statusfile, state)
        save(out / 'result.json', dict(state='FAIL', error=repr(exc)))
        raise
    finally:
        for child in children.values():
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    main()
