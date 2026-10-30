#!/usr/bin/env python3
"""Build actual GGML dispatch and check it under native-QBS Linux QEMU.

Functional integration only. This never supplies or replaces RTL timing data.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_ggml_segmented import verify_native_build
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from capture_host import validate_capture


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_log(text):
    native = 'GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 command_attempts=16 groups=2 value_decodes=256 executor_status=0'
    reject = 'GGML_RISCV_QUANT_KV status=1 mapping=0 memory=1 runtime_called=1 command_attempts=0 groups=0 value_decodes=0 executor_status=0'
    records = [line for line in text.splitlines() if line.startswith(
        ('QUANT_LIVE_', 'GGML_RISCV_QUANT_KV', 'GUEST_TEST_EXIT='))]
    require(not re.search(r'Assertion\b.*\bfailed|terminate called|Segmentation fault', text), 'Guest failure text')
    cursor = 0

    def exact(expected):
        nonlocal cursor
        require(cursor < len(records) and records[cursor] == expected, 'Wrong or missing record: ' + expected)
        cursor += 1

    def matched(pattern):
        nonlocal cursor
        match = re.fullmatch(pattern, records[cursor]) if cursor < len(records) else None
        require(match is not None, 'Wrong numerical/profile completion')
        cursor += 1
        return match

    for kind in ('q8_0', 'q4_0'):
        flags = []
        for repeat in range(2):
            exact(f'QUANT_LIVE_BEGIN kind={kind} mode=native repeat={repeat}')
            exact(native)
            end = matched(rf'QUANT_LIVE_END kind={kind} mode=native repeat={repeat} flags=(\d+) max_abs=([0-9.e+-]+)')
            require(int(end[1]) <= 31 and math.isfinite(float(end[2])), 'Nonfinite result or illegal flags')
            flags.append(int(end[1]))
        require(flags[0] == flags[1], 'Repeated flags changed')
        for mode in ('mask_fallback', 'thread_fallback', 'memory_fallback'):
            exact(f'QUANT_LIVE_BEGIN kind={kind} mode={mode}')
            if mode == 'mask_fallback':
                exact(reject)
            exact(f'QUANT_LIVE_END kind={kind} mode={mode}' + (' exact=1' if mode == 'mask_fallback' else ''))
        pattern = rf'QUANT_LIVE_PROFILE_PASS kind={kind} heads=12 kv_heads=2 outputs=1536 native_calls=2 ordinary_gold_max=([0-9.e+-]+) inputs_unchanged=1'
        require(math.isfinite(float(matched(pattern)[1])), 'Nonfinite profile maximum')
    exact('QUANT_LIVE_SUITE_PASS profiles=2 executor=native_qbs performance=not_measured')
    exact('GUEST_TEST_EXIT=0')
    require(cursor == len(records), 'Unknown or extra evidence records')
    return dict(state='LIVE_GGML_GRAPH_CHECKED', profiles=2, native_calls=4,
                native_command_attempts=64, fallback_cases=6, whole_model=False,
                rtl_performance=False)


def check_compile_sources(build, llama):
    commands = json.loads((build / 'compile_commands.json').read_text())
    required = {llama / 'ggml/src/ggml-cpu/arch/riscv' / name for name in
                ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp')}
    required.update({HERE / 'ggml_live/test.cpp', ROOT / 'software/akv/experimental/quantized_kv/runtime.c'})
    observed = {}
    for row in commands:
        path = Path(row['file'])
        path = (path if path.is_absolute() else Path(row['directory']) / path).resolve(strict=True)
        require(path.is_relative_to(llama) or path.is_relative_to(ROOT), 'Foreign compile source ' + str(path))
        if path in required:
            observed[path] = row.get('arguments') or shlex.split(row['command'])
    require(set(observed) == required, 'Missing native integration compile units')
    test_flags = observed[HERE / 'ggml_live/test.cpp']
    require('-UNDEBUG' in test_flags and all(i < test_flags.index('-UNDEBUG')
            for i, flag in enumerate(test_flags) if flag.startswith('-DNDEBUG')), 'Test assertions disabled')
    for name in ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp'):
        require('-DGGML_USE_RISCV_QUANT_KV' in observed[llama / 'ggml/src/ggml-cpu/arch/riscv' / name],
                'Quantized hook not compiled')
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=16)
    args = parser.parse_args()
    require(1 <= args.jobs <= 32, 'Jobs must be 1..32')
    out, build = args.output.resolve(), args.build.resolve()
    require(not out.is_relative_to(build), 'Separate control and build directories required')
    out.mkdir(parents=True, exist_ok=False)
    llama = Path('/home/wangwy/llama/llama.cpp')
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    qemu = ROOT / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
    tools = platform / 'tools/bin'
    toolchain = Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')
    capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None, build=str(build),
                 qemu=str(qemu), scope=__doc__)

    def save():
        atomic_json(out / 'status.json', state)

    def run(argv, name, timeout):
        def started(pid):
            state.update(state=name.upper(), child_pid=pid)
            save()
        atomic_json(out / (name + '.command.json'), list(map(str, argv)))
        try:
            code = run_command(list(map(str, argv)), out / (name + '.log'), timeout,
                               dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), started)
            require(code == 0, name + ' returned ' + str(code))
        finally:
            state['child_pid'] = None
            save()

    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    save()
    try:
        verify_native_build(qemu)
        sources = {Path(__file__).resolve(), HERE / 'capture_host.py', HERE / 'test_live_graph_check.py', toolchain, qemu,
                   qemu.parent / 'native-model-manifest.json', platform / 'images/Image',
                   platform / 'images/fw_dynamic.bin', Path('/usr/bin/cmake'), Path(sys.executable).resolve(),
                   ROOT / 'verification/qbs/run_ggml_segmented.py',
                   ROOT / 'verification/qbs/run_half_scale_soc.py',
                   ROOT / 'verification/qbs/run_tile_context_engine.py', HERE / 'layout.py'}
        compiler = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin')
        sources.update((compiler / name).resolve(strict=True) for name in ('riscv64-linux-gcc', 'riscv64-linux-g++'))
        sources.add((tools / 'riscv64-linux-gcc').resolve(strict=True))
        for directory in (llama / 'ggml', llama / 'cmake', ROOT / 'software/qbs',
                          ROOT / 'software/akv', HERE / 'ggml_live'):
            sources.update(p for p in directory.rglob('*') if p.is_file() and
                           (p.suffix in {'.c', '.cpp', '.h', '.hpp', '.S', '.cmake', '.in'} or p.name == 'CMakeLists.txt'))
        captures = {}
        receipt = json.loads((capture / 'result.json').read_text())
        for kind in ('q8_0', 'q4_0'):
            path = capture / ('capture-k-' + kind + '-v-q8_0')
            captures[kind] = validate_capture(path, kind)
            require(captures[kind] == receipt['captures'][kind], 'Real capture changed')
            sources.update(Path(p) for p in captures[kind]['file_sha256'])
        pins = hashes(sources)
        atomic_json(out / 'source-pins.json', pins)

        def unchanged():
            require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Live integration input drift')

        run(['/usr/bin/cmake', '-S', HERE / 'ggml_live', '-B', build,
             '-DLLAMA_SOURCE_DIR=' + str(llama),
             '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_EXE_LINKER_FLAGS=-static'], 'configure', 180)
        check_compile_sources(build, llama)
        run(['/usr/bin/cmake', '--build', build, '--target', 'ggml-quant-kv-live',
             '-j' + str(args.jobs)], 'build', 1800)
        unchanged()
        binary = build / 'ggml-quant-kv-live'
        require(binary.is_file(), 'Missing native graph test')
        cpio = platform / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        run([tools / 'riscv64-linux-gcc', '-march=rv64gc', '-mabi=lp64d', '-O2', '-static',
             HERE / 'ggml_live/init.c', '-o', out / 'init'], 'init-build', 120)
        listing = ['dir /dev 755 0 0', 'nod /dev/console 600 0 0 c 5 1',
                   f'file /init {out / "init"} 755 0 0', f'file /test {binary} 755 0 0']
        for kind, label in (('q8_0', 'q8'), ('q4_0', 'q4')):
            listing.append(f'dir /{label} 755 0 0')
            directory = capture / ('capture-k-' + kind + '-v-q8_0') / 'decode/block'
            for name in ('attn_q_input-0.bin', 'attn_k_input-0.bin', 'attn_v_input-0.bin',
                         'attn_mask_input-0.bin', 'kqv_out-0.bin'):
                listing.append(f'file /{label}/{name} {directory / name} 644 0 0')
        (out / 'initramfs.list').write_text('\n'.join(listing) + '\n')
        with (out / 'initramfs.cpio').open('wb') as target, (out / 'cpio.log').open('wb') as log:
            subprocess.run([cpio, out / 'initramfs.list'], stdout=target, stderr=log, check=True, timeout=60)
        pins.update(hashes([binary, build / 'CMakeCache.txt', build / 'compile_commands.json',
                           out / 'init', out / 'initramfs.list', out / 'initramfs.cpio', cpio]))
        atomic_json(out / 'source-pins.json', pins)
        unchanged()
        run([qemu, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
             '-bios', platform / 'images/fw_dynamic.bin', '-kernel', platform / 'images/Image',
             '-initrd', out / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'], 'qemu', 900)
        result = check_log((out / 'qemu.log').read_text(errors='replace').replace('\r\n', '\n'))
        unchanged()
        verify_native_build(qemu)
        result.update(state='PASS', current_inputs_match=True, log_sha256=digest(out / 'qemu.log'),
                      source_pins_sha256=digest(out / 'source-pins.json'))
        atomic_json(out / 'result.json', result)
        state.update(state='PASS', result=result)
    except BaseException as exc:
        state.update(state='INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL', error=repr(exc))
        atomic_json(out / 'result.json', dict(state=state['state'], error=repr(exc)))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
