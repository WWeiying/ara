#!/usr/bin/env python3
"""Private static link and bounded model test, without editing llama.cpp."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build
from check import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use independent verification/out output')
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, performance_measured=False)
    def save():
        atomic_json(out/'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def execute(argv, label, timeout):
        argv = list(map(str, argv))
        atomic_json(out/(label+'.command.json'), argv)
        state['state'] = label.upper()
        save()
        if run_command(argv, out/(label+'.log'), timeout, os.environ.copy(), started):
            raise RuntimeError(label+' failed or timed out')
        state['child_pid'] = None
        save()
    def interrupted(sig, _):
        raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    save()
    try:
        base = ROOT/'verification/out/grouped-pv-model-v2-20261026-01'
        build = out/'libraries'
        libs = build/'llama'
        model_builder = ROOT/'verification/akv/quantized_kv/grouped_pv/model_v2'
        gate = ROOT/'verification/qbs/combined_zvfh_m4/graphs/run-context-02'
        candidate = ROOT/'verification/out/q8k-combined-zvfh-compile-20261026-02/candidate.o'
        pins = {}
        for directory, manifest in ((base, 'source-pins.json'), (gate, 'manifest.json')):
            report = json.loads((directory/'result.json').read_text())
            if report['state'] != 'PASS' or report['log_sha256'] != digest(directory/'qemu.log'):
                raise ValueError('Prerequisite receipt/log identity')
            expected = report['source_pins_sha256'] if directory == base else report['manifest_sha256']
            if expected != digest(directory/manifest):
                raise ValueError('Prerequisite manifest identity')
            incoming = json.loads((directory/manifest).read_text())
            if any(name in pins and pins[name] != value for name, value in incoming.items()):
                raise ValueError('Conflicting prerequisite identities')
            pins.update(incoming)
            pins.update(hashes([directory/'result.json', directory/manifest, directory/'qemu.log']))
        if hashes(map(Path, pins)) != pins or pins.get(str(candidate)) != digest(candidate):
            raise ValueError('Prerequisite source/artifact drift')
        platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
        qemu = ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
        qemu_files = verify_native_build(qemu)
        cc = platform/'tools/bin/riscv64-linux-gcc'
        cxx = platform/'tools/bin/riscv64-linux-g++'
        cpio = platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        init_source = ROOT/'verification/akv/quantized_kv/model_live/init.c'
        disk = platform/'images/qwen2.5-q4km-capture.ext4'
        archives = [libs/'src/libllama.a', libs/'ggml/src/libggml.a',
                    libs/'ggml/src/libggml-cpu.a', libs/'ggml/src/libggml-base.a']
        helpers = [HERE/'test.cpp', HERE/'check.py', Path(__file__), init_source,
                   cc.resolve(), cxx.resolve(), cpio, qemu, *map(Path, qemu_files), disk,
                   platform/'images/Image', platform/'images/fw_dynamic.bin']
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):
                helpers.append(Path(path).resolve())
        current = hashes(helpers)
        if any(name in pins and pins[name] != sha for name, sha in current.items()):
            raise ValueError('Model source mismatch')
        pins.update(current)
        atomic_json(out/'source-pins.json', pins)
        # Rebuild intermediate archives: the earlier receipt pinned only its ELF.
        execute(['/usr/bin/cmake', '-S', model_builder, '-B', build,
                 '-DLLAMA_SOURCE_DIR=/home/wangwy/llama/llama.cpp',
                 '-DCMAKE_TOOLCHAIN_FILE=/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake',
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXE_LINKER_FLAGS=-static'], 'configure', 180)
        sys.path.insert(0, str(model_builder))
        spec = importlib.util.spec_from_file_location('accepted_model_builder', model_builder/'run_model.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.check_compile_sources(build, pins)
        execute(['/usr/bin/cmake', '--build', build, '--target', 'llama', '-j16'], 'libraries', 1800)
        builder.check_compile_sources(build, pins)
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Library source drift')
        pins.update(hashes([*archives, build/'CMakeCache.txt', build/'compile_commands.json']))
        atomic_json(out/'source-pins.json', pins)
        execute([cxx, '-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O3',
                 '-UNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
                 '-I/home/wangwy/llama/llama.cpp/include', '-I/home/wangwy/llama/llama.cpp/ggml/include',
                 '-c', HERE/'test.cpp', '-o', out/'test.o'], 'compile', 180)
        execute([cxx, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-static', out/'test.o', candidate,
                 *archives, '-ldl', '-lm', '-pthread', '-Wl,-Map='+str(out/'link.map'), '-o', out/'test'], 'link', 180)
        execute([cc, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', init_source, '-o', out/'init'], 'init', 120)
        listing = out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                           'dir /model 755 0 0\ndir /tmp 1777 0 0\n'+
                           f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
        pins.update(hashes([out/'test.o', out/'test', out/'init', out/'link.map', listing, out/'initramfs.cpio']))
        atomic_json(out/'source-pins.json', pins)
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Build drift')
        result = dict(state='READY_NOT_RUN', elf_sha256=digest(out/'test'), rtl_performance=False)
        if args.execute_reviewed:
            execute([qemu, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
                     '-smp', '1', '-m', '4G', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                     '-bios', platform/'images/fw_dynamic.bin', '-kernel', platform/'images/Image',
                     '-initrd', out/'initramfs.cpio', '-drive', f'file={disk},if=virtio,format=raw,readonly=on',
                     '-append', 'console=ttyS0 rdinit=/init'], 'qemu', 7200)
            result.update(check((out/'qemu.log').read_text()), log_sha256=digest(out/'qemu.log'))
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Execution drift')
        result.update(post_pins_match=True, source_pins_sha256=digest(out/'source-pins.json'))
        atomic_json(out/'result.json', result)
        state['state'] = result['state']
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out/'result.json', dict(state='FAIL', error=repr(exc)))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
