#!/usr/bin/env python3
"""One bounded thread-local FCSR diagnostic; no source/library rebuild or retry."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
GRAPH = HERE.parent / 'ggml'
sys.path.insert(0, str(GRAPH))
from run import digest, hashes, atomic_json, run_command, verify_native_build, QEMU, PLATFORM
from check_flags import check_log, require

FAILED = ROOT / 'verification/out/grouped-pv-ggml-20261026-01'
BUILD = ROOT / 'verification/out/grouped-pv-ggml-build-20261026-01'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / 'verification/out') and not out.exists(), 'Fresh verification/out required')
    require(not out.is_relative_to(FAILED) and not out.is_relative_to(BUILD), 'Keep failed evidence immutable')
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None)

    def save():
        atomic_json(out / 'status.json', state)

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    save()
    try:
        require(json.loads((FAILED / 'result.json').read_text())['state'] == 'FAIL', 'Wrong preserved run')
        original = json.loads((FAILED / 'source-pins.json').read_text())
        require(all(digest(Path(p)) == sha for p, sha in original.items()), 'Original graph inputs changed')
        fixture = FAILED / 'fixture-source/test.cpp'
        require(digest(fixture) == original[str(GRAPH / 'test.cpp')], 'Archived fixture identity differs')
        environment = json.loads((FAILED / 'environment.json').read_text())
        compiler = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-linux-g++')
        libraries = [BUILD / 'ggml/src' / name for name in ('libggml.a', 'libggml-cpu.a', 'libggml-base.a')]
        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        sources = {HERE / name for name in ('test.cpp', 'worker.py', 'check_flags.py', 'test_check_flags.py', 'README.md')}
        sources.update({FAILED / 'result.json', FAILED / 'status.json', FAILED / 'qemu.log',
                        FAILED / 'source-pins.json', FAILED / 'environment.json', FAILED / 'init',
                        FAILED / 'initramfs.list', FAILED / 'qemu.command.json', compiler.resolve(strict=True), cpio,
                        BUILD / 'CMakeCache.txt', BUILD / 'compile_commands.json',
                        BUILD / 'CMakeFiles/ggml-quant-kv-grouped-pv.dir/link.txt'})
        sources.update((FAILED / 'fixture-source').iterdir())
        sources.update(libraries)
        sources.update(verify_native_build(QEMU))
        pins = dict(original)
        pins.update(hashes(sources))
        atomic_json(out / 'input-pins.json', pins)

        def unchanged():
            require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Diagnostic input drift')

        def run(argv, name, timeout):
            def started(pid):
                state.update(state=name.upper(), child_pid=pid)
                save()
            atomic_json(out / (name + '.command.json'), list(map(str, argv)))
            try:
                require(run_command(list(map(str, argv)), out / (name + '.log'), timeout, environment, started) == 0,
                        name + ' failed')
            finally:
                state['child_pid'] = None
                save()

        unchanged()
        obj, binary = out / 'test.o', out / 'thread-flags'
        run([compiler, '-march=rv64gcv', '-mabi=lp64d', '-O3', '-DNDEBUG', '-UNDEBUG',
             '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror', '-std=c++17',
             '-DGGML_USE_CPU', '-I/home/wangwy/llama/llama.cpp/ggml/include',
             '-DTHREAD_FLAGS_FIXTURE="' + str(fixture) + '"', '-c', HERE / 'test.cpp', '-o', obj], 'compile', 120)
        run([compiler, '-march=rv64gcv', '-mabi=lp64d', '-O3', '-static', obj, '-o', binary,
             *libraries, '-lm', '-ldl'], 'link', 120)
        listing = []
        for line in (FAILED / 'initramfs.list').read_text().splitlines():
            if line.startswith('file /test '):
                line = f'file /test {binary} 755 0 0'
            listing.append(line)
        require(sum(line.startswith('file /test ') for line in listing) == 1, 'Missing or duplicate guest test')
        listing_path = out / 'initramfs.list'
        listing_path.write_text('\n'.join(listing) + '\n')
        with (out / 'initramfs.cpio').open('xb') as dest, (out / 'cpio.log').open('xb') as log:
            subprocess.run([cpio, listing_path], stdout=dest, stderr=log, env=environment, check=True, timeout=60)
        pins.update(hashes([obj, binary, listing_path, out / 'initramfs.cpio']))
        atomic_json(out / 'input-pins.json', pins)
        unchanged()
        argv = json.loads((FAILED / 'qemu.command.json').read_text())
        require(argv[0] == str(QEMU) and argv.count('-initrd') == 1, 'Wrong prior QEMU command')
        argv[argv.index('-initrd') + 1] = str(out / 'initramfs.cpio')
        run(argv, 'qemu', 300)
        checked = check_log((out / 'qemu.log').read_text())
        unchanged()
        verify_native_build(QEMU)
        checked.update(log_sha256=digest(out / 'qemu.log'), input_pins_sha256=digest(out / 'input-pins.json'),
                       elf_sha256=digest(binary), current_inputs_match=True)
        atomic_json(out / 'result.json', checked)
        state.update(state='DIAGNOSTIC_COMPLETE', result=checked)
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out / 'result.json', state)
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
