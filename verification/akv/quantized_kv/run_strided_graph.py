#!/usr/bin/env python3
"""Check actual GGML strided/contiguous quantized Attention under native-QBS QEMU.

Functional integration only, never RTL performance or whole-model evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from run_live_graph import HERE, ROOT, require, digest, hashes, atomic_json, run_command, verify_native_build
from capture_host import validate_capture


def check_compile_sources(build, llama):
    required = {llama / 'ggml/src/ggml-cpu/arch/riscv' / name for name in
                ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp')}
    required.update({HERE / 'ggml_strided/test.cpp',
                     ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'})
    observed = {}
    for row in json.loads((build / 'compile_commands.json').read_text()):
        path = Path(row['file'])
        path = (path if path.is_absolute() else Path(row['directory']) / path).resolve(strict=True)
        require(path.is_relative_to(llama) or path.is_relative_to(ROOT), 'Foreign compile source')
        if path in required:
            observed[path] = row.get('arguments') or shlex.split(row['command'])
    require(set(observed) == required, 'Missing native strided compile units')
    flags = observed[HERE / 'ggml_strided/test.cpp']
    require('-UNDEBUG' in flags and all(i < flags.index('-UNDEBUG') for i, flag in enumerate(flags)
                                      if flag.startswith('-DNDEBUG')), 'Test assertions disabled')
    for name in ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp'):
        require('-DGGML_USE_RISCV_QUANT_KV' in observed[llama / 'ggml/src/ggml-cpu/arch/riscv' / name],
                'Native quantized dispatch not compiled')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=16)
    args = parser.parse_args()
    require(1 <= args.jobs <= 32, 'Jobs must be 1..32')
    out, build = args.output.resolve(), args.build.resolve()
    require(not out.is_relative_to(build), 'Separate build and result directories required')
    out.mkdir(parents=True, exist_ok=False)
    llama = Path('/home/wangwy/llama/llama.cpp')
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    qemu = ROOT / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
    toolchain = Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')
    capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
    snapshot = HERE / 'llama_integration_strided_20261024'
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None, build=str(build), scope=__doc__)

    def save():
        atomic_json(out / 'status.json', state)

    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)

    def run(argv, name, timeout):
        def started(pid):
            state.update(state=name.upper(), child_pid=pid)
            save()
        atomic_json(out / (name + '.command.json'), list(map(str, argv)))
        try:
            code = run_command(list(map(str, argv)), out / (name + '.log'), timeout,
                               dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), started)
            require(code == 0, name + ' failed: ' + str(code))
        finally:
            state['child_pid'] = None
            save()

    save()
    try:
        from check_strided_graph import check_log
        verify_native_build(qemu)
        manifest = json.loads((snapshot / 'manifest.json').read_text())
        require(digest(snapshot / 'source.patch') == manifest['patch_sha256'], 'Private integration patch drift')
        require(str(llama) == manifest['source'] and all(digest(llama / name) == sha
                for name, sha in manifest['source_sha256'].items()), 'Private integration differs from snapshot')
        sources = {Path(__file__).resolve(), HERE / 'check_strided_graph.py', HERE / 'test_strided_graph_check.py',
                   HERE / 'run_live_graph.py', HERE / 'capture_host.py', HERE / 'layout.py',
                   snapshot / 'manifest.json', snapshot / 'source.patch', toolchain,
                   qemu, qemu.parent / 'native-model-manifest.json', platform / 'images/Image',
                   platform / 'images/fw_dynamic.bin', HERE / 'ggml_live/init.c',
                   ROOT / 'verification/qbs/run_ggml_segmented.py',
                   ROOT / 'verification/qbs/run_half_scale_soc.py',
                   ROOT / 'verification/qbs/run_tile_context_engine.py',
                   Path('/usr/bin/cmake'), Path(sys.executable).resolve(), capture / 'result.json',
                   capture / 'source-pins.json'}
        for name in ('riscv64-linux-gcc', 'riscv64-linux-g++'):
            sources.add((platform / 'tools/bin' / name).resolve(strict=True))
        for directory in (llama / 'ggml', llama / 'cmake', ROOT / 'software/qbs',
                          ROOT / 'software/akv', HERE / 'ggml_strided'):
            sources.update(p for p in directory.rglob('*') if p.is_file() and
                           (p.suffix in {'.c', '.cpp', '.h', '.hpp', '.S', '.cmake', '.in'} or p.name == 'CMakeLists.txt'))
        receipt = json.loads((capture / 'result.json').read_text())
        require(digest(capture / 'source-pins.json') == receipt['source_pins_sha256'], 'Capture receipt drift')
        for kind in ('q8_0', 'q4_0'):
            checked = validate_capture(capture / ('capture-k-' + kind + '-v-q8_0'), kind)
            require(checked == receipt['captures'][kind], 'Real capture changed')
            sources.update(Path(p) for p in checked['file_sha256'])
        pins = hashes(sources)
        atomic_json(out / 'source-pins.json', pins)

        def unchanged():
            require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Strided graph input drift')

        run(['/usr/bin/cmake', '-S', HERE / 'ggml_strided', '-B', build,
             '-DLLAMA_SOURCE_DIR=' + str(llama), '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain),
             '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXE_LINKER_FLAGS=-static'], 'configure', 180)
        check_compile_sources(build, llama)
        run(['/usr/bin/cmake', '--build', build, '--target', 'ggml-quant-kv-strided',
             '-j' + str(args.jobs)], 'build', 1800)
        unchanged()
        binary = build / 'ggml-quant-kv-strided'
        require(binary.is_file(), 'Missing native strided graph test')
        run([platform / 'tools/bin/riscv64-linux-gcc', '-march=rv64gc', '-mabi=lp64d', '-O2', '-static',
             HERE / 'ggml_live/init.c', '-o', out / 'init'], 'init-build', 120)
        cpio = platform / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        listing = ['dir /dev 755 0 0', 'nod /dev/console 600 0 0 c 5 1',
                   f'file /init {out / "init"} 755 0 0', f'file /test {binary} 755 0 0']
        for kind, label in (('q8_0', 'q8'), ('q4_0', 'q4')):
            listing.append(f'dir /{label} 755 0 0')
            directory = capture / ('capture-k-' + kind + '-v-q8_0') / 'decode/block'
            for name in ('attn_q_input-0.bin', 'attn_k_input-0.bin', 'attn_v_input-0.bin',
                         'attn_mask_input-0.bin', 'kqv_out-0.bin'):
                listing.append(f'file /{label}/{name} {directory / name} 644 0 0')
        listing_path = out / 'initramfs.list'
        listing_path.write_text('\n'.join(listing) + '\n')
        with (out / 'initramfs.cpio').open('wb') as target, (out / 'cpio.log').open('wb') as log:
            subprocess.run([cpio, listing_path], stdout=target, stderr=log, check=True, timeout=60)
        pins.update(hashes([binary, build / 'CMakeCache.txt', build / 'compile_commands.json',
                           out / 'init', listing_path, out / 'initramfs.cpio', cpio]))
        atomic_json(out / 'source-pins.json', pins)
        unchanged()
        run([qemu, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
             '-bios', platform / 'images/fw_dynamic.bin', '-kernel', platform / 'images/Image',
             '-initrd', out / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'], 'qemu', 900)
        result = check_log((out / 'qemu.log').read_text().replace('\r\n', '\n'))
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
