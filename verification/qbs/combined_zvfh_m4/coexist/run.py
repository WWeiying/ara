#!/usr/bin/env python3
"""Bounded context/alias/barrier coexistence checks; no performance claims."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import (verify_native_build, check_context_dispatch,
                                check_alias_dispatch, check_barrier_dispatch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suites', nargs='+', choices=('context', 'alias', 'barrier'),
                        default=['context', 'alias', 'barrier'])
    args = parser.parse_args()
    if len(set(args.suites)) != len(args.suites):
        raise ValueError('Duplicate suites')
    build, out = args.build.resolve(strict=True), args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use private verification/out')
    report = json.loads((build/'build.json').read_text())
    pins = json.loads((build/'manifest.json').read_text())
    if report['state'] != 'READY' or digest(build/'manifest.json') != report['manifest_sha256'] or \
            hashes(map(Path, pins)) != pins:
        raise ValueError('Build drift')
    qemu = ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    sources = [Path(__file__), build/'build.json', build/'manifest.json', qemu,
               *map(Path, verify_native_build(qemu)), platform/'images/Image', platform/'images/fw_dynamic.bin']
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):
            sources.append(Path(path).resolve())
    pins.update(hashes(sources))
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out/'manifest.json', pins)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, completed=[])
    def save():
        atomic_json(out/'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def interrupted(sig, _):
        raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    save()
    checks = dict(context=check_context_dispatch, alias=check_alias_dispatch, barrier=check_barrier_dispatch)
    results = {}
    try:
        for suite in args.suites:
            check = checks[suite]
            state.update(state='RUNNING', suite=suite)
            save()
            command = list(map(str, [qemu, '-M', 'virt', '-cpu',
                'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true', '-smp', '1', '-m', '512M',
                '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                '-bios', platform/'images/fw_dynamic.bin', '-kernel', platform/'images/Image',
                '-initrd', build/(suite+'.cpio'), '-append', 'console=ttyS0 rdinit=/init']))
            atomic_json(out/(suite+'.command.json'), command)
            log = out/(suite+'.log')
            if run_command(command, log, 900, os.environ.copy(), started):
                raise RuntimeError(suite+' guest failed or timed out')
            text = log.read_text()
            if 'GUEST_TEST_EXIT=0' not in text or re.findall(
                    r'QBS_GRAPH_RUN_END segment=(\d+) wide=(\d+) exit=(\d+)', text) != [
                    ('0','0','0'), ('3','0','0'), ('256','0','0'), ('256','0','0')]:
                raise ValueError(suite+' incomplete guest')
            if re.search(r'Assertion .*failed|QBS.*FAIL|Kernel panic|Illegal instruction', text):
                raise ValueError(suite+' failure diagnostic')
            check(text)
            prep = re.findall(r'GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=(\d+) path=(\w+) k=(\d+)', text)
            if suite == 'context' and (len(prep) != 16 or any(enabled != '1' or path != 'rvv' or k != '1792'
                                                       for enabled, path, k in prep)):
                raise ValueError('M4 combined vector path was not exercised as expected')
            if suite != 'context' and prep:
                raise ValueError('Unexpected M4 preparation in M1 mutation/barrier tests')
            if hashes(map(Path, pins)) != pins:
                raise ValueError('Execution source drift')
            results[suite] = dict(state='PASS', log_sha256=digest(log), m4_vector_calls=len(prep))
            state['completed'].append(suite)
            state['child_pid'] = None
            save()
        atomic_json(out/'result.json', dict(state='PASS', suites=results, rtl_performance=False,
                                          manifest_sha256=digest(out/'manifest.json')))
        state['state'] = 'PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out/'result.json', dict(state='FAIL', error=repr(exc), completed=results))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
