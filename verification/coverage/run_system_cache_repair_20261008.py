#!/usr/bin/env python3
"""Finish one historical timeout after focused repair acceptance; no full suite."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

import build_memory_vl0_repair as builder
import audit_system_cache_repair as checker

base = builder.base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--acceptance-unit', required=True)
    args = parser.parse_args()
    base.check_service()
    out = base.checked_output(args.output)
    out.mkdir(exist_ok=False)
    state = dict(status='WAITING_ACCEPTANCE', case='system_gap30_cache',
                 acceptance=str(args.acceptance.resolve()), full_regression_started=False)
    base.save(out / 'status.json', state)
    try:
        pins = base.pins(Path(m.__file__) for m in list(sys.modules.values())
            if getattr(m, '__file__', None) and
            str(Path(m.__file__).resolve()).startswith(str(base.ROOT / 'verification'))
            and Path(m.__file__).is_file())
        deadline = time.monotonic() + 10800
        while True:
            observed = subprocess.run(['systemctl', '--user', 'show', args.acceptance_unit,
                '--property=ActiveState', '--property=MainPID', '--property=ExecMainStatus',
                '--property=LoadState'], capture_output=True, text=True, check=True, timeout=10)
            service = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
            if service.get('LoadState') == 'not-found':
                raise RuntimeError('missing acceptance service')
            if service.get('ActiveState') in ('inactive', 'failed') and service.get('MainPID') == '0':
                if service.get('ExecMainStatus') != '0' or base.read(args.acceptance / 'status.json')['status'] != 'PASS':
                    raise RuntimeError('focused acceptance did not pass; no automatic cache dispatch')
                break
            if service.get('ActiveState') != 'active' or time.monotonic() >= deadline:
                raise RuntimeError('acceptance wait failed or exhausted')
            time.sleep(60)
        image_dir = args.image_directory.resolve(strict=True)
        if base.read(image_dir / 'build-status.json')['status'] != 'PASS':
            raise RuntimeError('unqualified build')
        image = image_dir / 'sim/simv'
        pins.update(base.read(image_dir / 'build-source-pins.json'))
        pins.update(base.read(image_dir / 'build-image.json'))
        accepted_pins = base.read(args.acceptance / 'source-pins.json')
        for path, value in base.read(image_dir / 'build-image.json').items():
            if accepted_pins.get(path) != value:
                raise RuntimeError('acceptance used a different image')
        shutil.copyfile(checker.source() / 'input.elf', out / 'input.elf')
        if base.sha256(out / 'input.elf') != checker.ELF_SHA:
            raise RuntimeError('different original cache ELF')
        pins.update(base.pins([checker.source() / 'input.elf', out / 'input.elf']))
        base.check(pins)
        base.save(out / 'source-pins.json', pins)
        command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=system_gap30_cache',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
            '-cm_name', 'system_gap30_cache']
        base.save(out / 'command.json', dict(command=command, timeout_s=1800))
        state.update(status='RUNNING', image=str(image))
        base.save(out / 'status.json', state)
        with (out / 'console.log').open('w') as log:
            with subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT) as process:
                base.save(out / 'started.json', dict(pid=process.pid, image=str(image),
                    image_sha256=base.sha256(image), elf_sha256=checker.ELF_SHA))
                try:
                    result = process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise
                if result != 0:
                    raise RuntimeError('simulator failed: ' + str(result))
        base.check(pins)
        evidence = checker.audit(out)
        base.save(out / 'audit.json', evidence)
        state.update(status='PASS', checks=evidence['checks'], last_cycle=evidence['last_cycle'])
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
    base.save(out / 'status.json', state)
    return 0 if state['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
