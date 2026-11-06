#!/usr/bin/env python3
"""Event-driven gate: memory pair first, then bounded QBS/AKV handoff pair."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, RUNS

SOC_HASH = {
    128: 'c0b7dbe24f03583851d64146da5bbac06341b9f24a70d0036e3aea0294f1a195',
    256: 'f406f967a87c2c198656fe4aa933d34330aaf40fd230adfa331f70347f5c93bd',
}
MEMORY_ELF = 'a63841ff39b370d06dbe039273ab4dd339fbd43c201ad6515416fa7f45bcd087'
HANDOFF = RUNS / 'e2e_wide_soc_handoff_smoke_build_20261106_01'
HANDOFF_HASH = '8e2df9b622fb4df7ba3936f4a558b0c7dea1da138b7ef1a7be9459f09f2b9b60'
HANDOFF_STATE = 'WIDE_SOC_HANDOFF_COMMITTED_ELF_BUILT_NOT_EXECUTED'
MEMORY = tuple(RUNS / f'e2e_physical_memory{w}_20261106_01' for w in (128, 256))


def require_terminal(root, width, elf_sha):
    path = root / 'result.json'
    if not path.exists(): return None
    value = json.loads(path.read_text())
    require(value['state'] == 'PHYSICAL_WIDE_SOC_SMOKE_PASS' and value['post_pins_match'] and
            value['independent_protocol_checked'] and value['width'] == width and
            value['elf_sha256'] == elf_sha, 'Smoke failed or has wrong work/image: ' + str(root))
    require(digest(root / 'source-pins.json') == value['source_pins_sha256'], 'Smoke pins changed')
    verify_pins(json.loads((root / 'source-pins.json').read_text()))
    verify_pins(value['artifacts'])
    return value


def wait_memory(timeout=7500):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]; libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    require(fd >= 0, 'inotify unavailable')
    try:
        for root in MEMORY:
            require(root.is_dir() and libc.inotify_add_watch(fd, os.fsencode(root), 0x8 | 0x80) >= 0,
                    'Existing memory-worker watch unavailable')
        deadline = time.monotonic() + timeout
        while True:
            # Workers publish result.json once at terminal. Observe their close
            # event rather than treating an unfinished write as a terminal error.
            try:
                values = [require_terminal(root, width, MEMORY_ELF)
                          for root, width in zip(MEMORY, (128, 256))]
            except json.JSONDecodeError:
                values = [None]
            if all(values): return values
            remaining = deadline-time.monotonic()
            require(remaining > 0 and select.select([fd], [], [], remaining)[0], 'Memory completion deadline')
            os.read(fd, 65536)
    finally: os.close(fd)


def handoff_adapter(original, out):
    """Normalize producer state spelling only, never modify/reclassify it."""
    require(digest(original / 'result.json') == HANDOFF_HASH, 'Unreviewed handoff producer')
    value = json.loads((original / 'result.json').read_text())
    require(value['state'] == HANDOFF_STATE and value['post_pins_match'] and
            value['expected_exceptions'] == 0 and value['skip_is_not_acceptance'], 'Handoff not built/admitted')
    require(digest(original / 'source-pins.json') == value['source_pins_sha256'], 'Handoff source inventory')
    verify_pins(json.loads((original / 'source-pins.json').read_text())); verify_pins(value['artifacts'])
    out.mkdir(exist_ok=False)
    shutil.copyfile(original / 'source-pins.json', out / 'source-pins.json')
    result = dict(value, state='WIDE_SOC_HANDOFF_SMOKE_ELF_BUILT_NOT_EXECUTED',
                  producer_state=value['state'], producer_result=str(original / 'result.json'),
                  producer_result_sha256=HANDOFF_HASH, producer_relabelled=False,
                  adaptation='Build-state spelling only; same ELF, sources, loader admission and artifacts')
    result['artifacts'] = dict(value['artifacts'], **{
        str(original / 'result.json'): HANDOFF_HASH,
        str(original / 'source-pins.json'): value['source_pins_sha256']})
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification campaign')
    out.mkdir(parents=True, exist_ok=False)
    pins = {str(path): digest(path) for path in (
        Path(__file__), HERE / 'test_continue_wide_soc.py', HERE / 'run_wide_soc_smoke.py',
        HERE / 'test_wide_soc_smoke.py', HERE / 'audit.py', Path(sys.executable))}
    children = {}
    result = dict(state='PREPARING', performance_measured=False, synthesis_run=False,
                  model_execution_accepted=False, real_pmp_accepted=False)

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    try:
        adapter = out / 'handoff-program'
        program = handoff_adapter(HANDOFF, adapter)
        pins[str(adapter / 'result.json')] = digest(adapter / 'result.json')
        pins[str(adapter / 'source-pins.json')] = digest(adapter / 'source-pins.json')
        for width, sha in SOC_HASH.items():
            soc = RUNS / f'e2e_physical_wide_soc{width}_20261106_01'
            require(digest(soc / 'result.json') == sha, 'Wrong compiled full processor')
            pins[str(soc / 'result.json')] = sha
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result.update(state='WAITING_MEMORY_RESULT_EVENTS', memory_workers=list(map(str, MEMORY)))
        save(); memory_results = wait_memory(); verify_pins(pins)
        result['state'] = 'RUNNING_HANDOFF_PAIR'; save()
        def execute(width):
            soc = RUNS / f'e2e_physical_wide_soc{width}_20261106_01'
            target = out / f'handoff{width}'
            argv = [sys.executable, '-B', str(HERE / 'run_wide_soc_smoke.py'),
                    '--soc', str(soc), '--soc-sha', SOC_HASH[width],
                    '--program', str(adapter), '--program-sha', pins[str(adapter / 'result.json')],
                    '--kind', 'handoff', '--timeout', '2700', '--output', str(target)]
            (out / f'command{width}.json').write_text(json.dumps(argv, indent=2) + '\n')
            with (out / f'worker{width}.log').open('xb') as stream:
                child = subprocess.Popen(argv, cwd=HERE, stdout=stream, stderr=subprocess.STDOUT)
                children[width] = child
                code = child.wait()
            require(code == 0, 'Handoff worker failed: ' + str(width))
            return require_terminal(target, width, program['elf_sha256'])
        completed = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(execute, width): width for width in (128, 256)}
            try:
                for future in as_completed(futures): completed[futures[future]] = future.result()
            except BaseException:
                for child in tuple(children.values()):
                    if child.poll() is None: child.terminate()
                raise
        verify_pins(pins)
        result.update(state='PHYSICAL_WIDE_MEMORY_AND_HANDOFF_PASS',
            memory=[dict(width=v['width'], elf_sha256=v['elf_sha256'], measured=v['measured']) for v in memory_results],
            handoff=[dict(width=w, elf_sha256=v['elf_sha256'], measured=v['measured']) for w,v in sorted(completed.items())],
            post_pins_match=True,
            limitations=['Focused scalar/RVV and QBS/AKV ownership checks, not full ISA or format signoff',
                         'No SDK/model performance, real PMP or Linux wide-path acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save()
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    def stop(sig, frame): raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    main(parser.parse_args().output)
