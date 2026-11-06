#!/usr/bin/env python3
"""Seal inputs now; launch same-ELF SDK pairs after actual memory/handoff PASS."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

from audit import digest, require, verify_pins
import run_supply_sdk as runner
from prepare_wide_soc import HERE, RUNS


def wait_gate(pins, timeout=10800):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]; libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    require(fd >= 0, 'Event notification unavailable')
    try:
        require(libc.inotify_add_watch(fd, os.fsencode(runner.GATE), 0x8 | 0x80) >= 0,
                'Existing gate directory required')
        deadline = time.monotonic() + timeout
        while True:
            if (runner.GATE / 'result.json').exists():
                try: return runner.acceptance_gate(pins)
                except json.JSONDecodeError: pass
            remaining = deadline - time.monotonic()
            require(remaining > 0 and select.select([fd], [], [], remaining)[0], 'Gate completion deadline')
            os.read(fd, 65536)
    finally: os.close(fd)


def collect(root, kind, width):
    value = json.loads((root / 'result.json').read_text())
    require(value['state'] == 'PHYSICAL_SUPPLY_SDK_PASS' and value['post_pins_match'] and
            value['kind'] == kind and value['width'] == width and value['performance_measured'] and
            value['independent_protocol_checked'], 'Unaccepted SDK result')
    require(digest(root / 'source-pins.json') == value['source_pins_sha256'], 'SDK source inventory differs')
    verify_pins(json.loads((root / 'source-pins.json').read_text())); verify_pins(value['artifacts'])
    config, pins = runner.inputs(kind, width); verify_pins(pins)
    soc, program = config['soc'], config['program']
    require(value['simv'] == soc['simv'] and value['image_pins'] == soc['image_pins'] and
            value['elf_sha256'] == program['elf_sha256'], 'SDK executable identity differs')
    work = root / 'work'; text = (work / 'run.vcs.log').read_text()
    require(runner.check_platform(text, width) == value['platform'] and
            runner.checker.check(text, kind, width, runner.checker.oracle(config['build'], kind)) == value['measured'],
            'Independent raw SDK replay differs')
    protocol = json.loads((work / 'uvm_result.json').read_text())
    require(protocol['status'] == 'PASS' and protocol['log_sha256'] == digest(work / 'run.vcs.log') and
            protocol['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and
            protocol['elf_sha256'] == program['elf_sha256'] and protocol['sim_image_sha256'] == soc['image_pins'],
            'Protocol evidence identity differs')
    return value


def main(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification campaign required')
    out.mkdir(parents=True, exist_ok=False)
    result = dict(state='PREPARING', performance_measured=False, whole_model=False, synthesis_run=False)
    pins, children, pairs = {}, {}, {}
    def save(): (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
    def inventory():
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    try:
        for kind in runner.PROGRAMS:
            elfs = set()
            for width in runner.SOC_HASH:
                config, candidate = runner.inputs(kind, width); elfs.add(config['program']['elf_sha256'])
                for path, sha in candidate.items(): runner.bind(pins, path, sha)
            require(len(elfs) == 1, 'Hardware pair must use identical SDK ELF')
        for path in (Path(__file__), HERE / 'test_continue_supply.py'): runner.bind(pins, path)
        verify_pins(pins); inventory()
        result['state'] = 'WAITING_PHYSICAL_ACCEPTANCE_EVENT'; save()
        result['prerequisite_result_sha256'] = wait_gate(pins); verify_pins(pins); inventory()
        for kind in runner.PROGRAMS:
            result.update(state='RUNNING_' + kind.upper() + '_PAIR', completed_pairs=pairs); save()
            def execute(width):
                target = out / (kind + str(width))
                argv = [sys.executable, '-B', str(HERE / 'run_supply_sdk.py'), '--kind', kind, '--width', str(width),
                        '--output', str(target), '--timeout', '7200', '--execute-reviewed']
                (out / (kind + str(width) + '.command.json')).write_text(json.dumps(argv, indent=2) + '\n')
                with (out / (kind + str(width) + '.worker.log')).open('xb') as stream:
                    child = subprocess.Popen(argv, cwd=HERE, stdout=stream, stderr=subprocess.STDOUT)
                    children[width] = child; code = child.wait()
                require(code == 0, 'SDK worker failed: ' + kind + str(width))
                return collect(target, kind, width)
            values = {}
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(execute, width): width for width in (128, 256)}
                try:
                    for future in as_completed(futures): values[futures[future]] = future.result()
                except BaseException:
                    for child in tuple(children.values()):
                        if child.poll() is None: child.terminate()
                    raise
            require(values[128]['elf_sha256'] == values[256]['elf_sha256'], 'Unequal actual ELF')
            pairs[kind] = runner.checker.paired(values[128]['measured'], values[256]['measured'], kind)
            pairs[kind]['results'] = {str(w): dict(path=str(out / (kind + str(w)) / 'result.json'),
                sha256=digest(out / (kind + str(w)) / 'result.json')) for w in (128, 256)}
            verify_pins(pins)
        result.update(state='PHYSICAL_SUPPLY_SDK_PAIR_PASS', completed_pairs=pairs, performance_measured=True,
                      post_pins_match=True, source_pins_sha256=digest(out / 'source-pins.json'),
                      limits=['One reset trial per width/workload; no run-to-run distribution',
                              'Real SDK work with preparation; not whole-model performance',
                              'Physical SRAM platform comparison, not unchanged external-DDR bandwidth',
                              'Same-platform best RVV timing and translated-path acceptance still separate'])
    except BaseException as exc:
        result.update(state='FAIL', completed_pairs=pairs, error=repr(exc)); raise
    finally:
        save(); (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    def stop(sig, _frame): raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    main(parser.parse_args().output)
