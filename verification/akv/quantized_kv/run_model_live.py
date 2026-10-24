#!/usr/bin/env python3
"""Native-QBS Linux model generation, not an RTL performance experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from run_live_graph import HERE, ROOT, require, digest, hashes, atomic_json, run_command, verify_native_build

PRIOR = ROOT / 'verification/out/akv-quantkv-ggml-interleave-20261024-05'
MODEL_PATH = '/models/qwen2.5-1.5b-instruct-q4_k_m.gguf'


def wait_initial_build(pid, build):
    if not pid:
        return
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        try:
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        except FileNotFoundError:
            argv = []
        if argv:
            require(str(build).encode() in argv and b'--build' in argv and b'quant-kv-model-live' in argv,
                    'Initial build owner changed')
        require(bool(select.select([fd], [], [], 1800)[0]), 'Initial build wait expired; no restart')
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-owner-pid', type=int, default=0)
    parser.add_argument('--timeout', type=int, default=3600)
    args = parser.parse_args()
    require(1 <= args.timeout <= 7200, 'Bound must be 1..7200 seconds')
    out, build = args.output.resolve(), args.build.resolve()
    require(not out.is_relative_to(build), 'Separate build and result directories required')
    out.mkdir(parents=True, exist_ok=False)
    llama = Path('/home/wangwy/llama/llama.cpp')
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    model = Path('/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf')
    disk = platform / 'images/qwen2.5-q4km-capture.ext4'
    qemu = ROOT / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
    toolchain = Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None, build=str(build),
                 qemu=str(qemu), scope=__doc__)
    def save(): atomic_json(out / 'status.json', state)
    def interrupted(sig, _frame): raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('LD_PRELOAD', None)
    def run(argv, name, timeout):
        def started(pid):
            state.update(state=name.upper(), child_pid=pid)
            save()
        atomic_json(out / (name + '.command.json'), list(map(str, argv)))
        try:
            require(run_command(list(map(str, argv)), out / (name + '.log'), timeout, env, started) == 0,
                    name + ' failed')
        finally:
            state['child_pid'] = None
            save()
    save()
    try:
        from check_model_live import check_log
        require(json.loads((PRIOR / 'result.json').read_text())['state'] == 'PASS', 'Interleaving prerequisite not accepted')
        pins = json.loads((PRIOR / 'source-pins.json').read_text())
        receipt = json.loads((PRIOR / 'result.json').read_text())
        require(digest(PRIOR / 'source-pins.json') == receipt['source_pins_sha256'], 'Prior source receipt drift')
        sources = {Path(__file__), HERE / 'check_model_live.py', HERE / 'test_model_live_check.py',
                   PRIOR / 'result.json', PRIOR / 'status.json', PRIOR / 'source-pins.json',
                   llama / 'CMakeLists.txt', model, disk, toolchain, Path('/usr/sbin/debugfs'),
                   Path('/usr/bin/timeout')}
        for directory in (llama / 'src', llama / 'include', llama / 'cmake', llama / 'vendor', HERE / 'model_live'):
            sources.update(p for p in directory.rglob('*') if p.is_file() and
                           (p.suffix in {'.c', '.cpp', '.h', '.hpp', '.S', '.cmake', '.in'} or p.name == 'CMakeLists.txt'))
        pins.update(hashes(sources))
        def unchanged(): require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Model execution input drift')
        unchanged()
        atomic_json(out / 'source-pins.json', pins)
        state.update(state='WAITING_INITIAL_BUILD', initial_build_owner=args.build_owner_pid)
        save()
        wait_initial_build(args.build_owner_pid, build)
        unchanged()
        run(['/usr/bin/cmake', '-S', HERE / 'model_live', '-B', build,
             '-DLLAMA_SOURCE_DIR=' + str(llama), '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain),
             '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXE_LINKER_FLAGS=-static'], 'configure', 180)
        run(['/usr/bin/cmake', '--build', build, '--target', 'quant-kv-model-live', '-j16'], 'build', 1800)
        unchanged()
        commands = json.loads((build / 'compile_commands.json').read_text())
        needed = {HERE / 'model_live/test.cpp', llama / 'src/llama-context.cpp', llama / 'src/llama-model.cpp',
                  llama / 'ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp',
                  ROOT / 'software/akv/experimental/quantized_kv/runtime.c'}
        actual = {Path(row['file']).resolve(strict=True) for row in commands}
        require(needed <= actual and all(p.is_relative_to(ROOT) or p.is_relative_to(llama) for p in actual),
                'Missing/foreign full-model compile units')
        # Stream the model from the immutable disk: a same filename is not
        # sufficient evidence that the guest loads the selected host GGUF.
        state.update(state='CHECKING_MODEL_DISK')
        with (out / 'disk-model.log').open('xb') as log:
            process = subprocess.Popen(['/usr/bin/timeout', '180', '/usr/sbin/debugfs', '-R',
                                        'cat ' + MODEL_PATH, disk], stdout=subprocess.PIPE, stderr=log)
            state['child_pid'] = process.pid
            save()
            value, length = hashlib.sha256(), 0
            try:
                for chunk in iter(lambda: process.stdout.read(4 * 1024 * 1024), b''):
                    value.update(chunk)
                    length += len(chunk)
                require(process.wait() == 0, 'Cannot read the guest model from the disk')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
                state['child_pid'] = None
                save()
        require(length == model.stat().st_size and value.hexdigest() == pins[str(model)], 'Disk model differs from host GGUF')
        atomic_json(out / 'model-identity.json', dict(host=str(model), guest=MODEL_PATH,
                    bytes=length, sha256=value.hexdigest(), disk=str(disk), disk_sha256=pins[str(disk)]))
        compiler = platform / 'tools/bin/riscv64-linux-gcc'
        run([compiler, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', HERE / 'model_live/init.c',
             '-o', out / 'init'], 'init-build', 120)
        binary = build / 'quant-kv-model-live'
        listing = out / 'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\n'
                           f'file /init {out / "init"} 755 0 0\nfile /test {binary} 755 0 0\n')
        cpio = platform / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        with (out / 'initramfs.cpio').open('wb') as dest, (out / 'cpio.log').open('wb') as log:
            subprocess.run([cpio, listing], stdout=dest, stderr=log, check=True, timeout=60)
        pins.update(hashes([binary, build / 'CMakeCache.txt', build / 'compile_commands.json',
                            out / 'init', listing, out / 'initramfs.cpio', out / 'model-identity.json']))
        atomic_json(out / 'source-pins.json', pins)
        unchanged()
        verify_native_build(qemu)
        run([qemu, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp', '1', '-m', '4G', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
             '-bios', platform / 'images/fw_dynamic.bin', '-kernel', platform / 'images/Image',
             '-initrd', out / 'initramfs.cpio', '-drive', f'file={disk},if=virtio,format=raw,readonly=on',
             '-append', 'console=ttyS0 rdinit=/init'], 'qemu', args.timeout)
        checked = check_log((out / 'qemu.log').read_text().replace('\r\n', '\n'))
        unchanged()
        verify_native_build(qemu)
        checked.update(state='PASS', current_inputs_match=True, log_sha256=digest(out / 'qemu.log'),
                       source_pins_sha256=digest(out / 'source-pins.json'), model_sha256=value.hexdigest())
        atomic_json(out / 'result.json', checked)
        state.update(state='PASS', result=checked)
    except BaseException as exc:
        state.update(state='INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL', error=repr(exc))
        atomic_json(out / 'result.json', dict(state=state['state'], error=repr(exc)))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__': main()
