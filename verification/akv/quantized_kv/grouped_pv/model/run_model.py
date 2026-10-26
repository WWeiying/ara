#!/usr/bin/env python3
"""Bounded short-model OFF/ON grouped comparison, after fresh graph acceptance."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
LEGACY = ROOT / 'verification/akv/quantized_kv'
GRAPH = HERE.parent / 'ggml'
sys.path.insert(0, str(LEGACY))
from run_model_live import MODEL_PATH, digest, hashes, atomic_json, run_command, verify_native_build
from run_model_strided import json_file, check_pins
from check_model import check_log, require

LLAMA = Path('/home/wangwy/llama/llama.cpp')
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
QEMU = ROOT / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
MODEL = Path('/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf')
DISK = PLATFORM / 'images/qwen2.5-q4km-capture.ext4'
TOOLCHAIN = Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')
TARGET = 'quant-kv-model-grouped'


def prerequisite(gate):
    expected = json_file(HERE / 'graph_receipt.json')
    require(str(gate) == expected['path'] and all(digest(gate / name) == sha for name, sha in expected['sha256'].items()),
            'Use the explicitly accepted graph02 receipt/log/pins')
    receipt, status = json_file(gate / 'result.json'), json_file(gate / 'status.json')
    require(receipt.get('state') == status.get('state') == 'PASS' and status.get('child_pid') is None,
            'Fresh grouped graph prerequisite is not terminal PASS')
    require(receipt.get('current_inputs_match') is True and receipt.get('whole_model') is False and
            receipt.get('rtl_performance') is False, 'Wrong graph evidence scope')
    require(receipt.get('log_sha256') == digest(gate / 'qemu.log') and
            receipt.get('source_pins_sha256') == digest(gate / 'source-pins.json'), 'Graph receipt identity mismatch')
    pins = json_file(gate / 'source-pins.json')
    critical = [GRAPH / name for name in ('run.py', 'check.py', 'test.cpp', 'external_snapshot.json')]
    critical.extend(LLAMA / name for name in ('ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp',))
    critical.extend(ROOT / 'software/akv/experimental/quantized_kv' / name for name in
                    ('online.h', 'grouped_pv.h', 'runtime_strided.c', 'ggml_entry_strided.h'))
    require(all(str(path) in pins for path in critical), 'Graph prerequisite omits current producer/checker')
    check_pins(pins)
    spec = importlib.util.spec_from_file_location('accepted_grouped_graph_checker', GRAPH / 'check.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checked = checker.check_log((gate / 'qemu.log').read_text().replace('\r\n', '\n'))
    require(checked['native_calls'] == 32 and checked['native_command_attempts'] == 320 and
            checked['key_panels'] == 80 and checked['key_bytes'] == 221312 and
            len(checked['thread_csr_observations']) == 4, 'Wrong graph prerequisite coverage')
    require(all(receipt.get(key) == value for key, value in checked.items() if key != 'state'),
            'Raw graph checker disagrees with receipt')
    require(receipt.get('elf_sha256') in pins.values(), 'Graph receipt ELF omitted from pins')
    artifacts = hashes([gate / name for name in ('result.json', 'status.json', 'qemu.log', 'source-pins.json')])
    require(all(name not in pins or pins[name] == sha for name, sha in artifacts.items()), 'Graph evidence drift')
    return dict(pins, **artifacts)


def model_inputs():
    snapshot = json_file(HERE / 'external_snapshot.json')
    require(snapshot['schema'] == 1 and snapshot['source'] == str(LLAMA), 'Wrong model snapshot')
    require(digest(GRAPH / 'external_snapshot.json') == snapshot['graph_snapshot_sha256'] and
            digest(LLAMA / 'ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp') == snapshot['adapter_sha256'],
            'Adapter/graph snapshot changed')
    names = subprocess.run(['/usr/bin/rg', '--files', *snapshot['inventory']], cwd=LLAMA,
                           env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, capture_output=True,
                           text=True, check=True, timeout=30).stdout.splitlines()
    require(names and len(names) == len(set(names)), 'Bad model source inventory')
    pins, rows = {}, []
    for name in sorted(names):
        path = LLAMA / name
        require(path.resolve(strict=True).is_relative_to(LLAMA), 'Source escapes llama tree')
        sha = digest(path)
        pins[str(path)] = sha
        rows.append(f'{sha}  {name}\n')
    require(hashlib.sha256(''.join(rows).encode()).hexdigest() == snapshot['tree_sha256'], 'Model source snapshot drift')
    return pins


def check_compile_sources(build, pins):
    arch = LLAMA / 'ggml/src/ggml-cpu/arch/riscv'
    required = {arch / name for name in ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp')}
    required.update({HERE / 'test.cpp', LLAMA / 'src/llama-context.cpp', LLAMA / 'src/llama-model.cpp',
                     ROOT / 'software/qbs/src/qbs_runtime.c',
                     ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'})
    observed = {}
    for row in json_file(build / 'compile_commands.json'):
        path = Path(row['file'])
        path = (path if path.is_absolute() else Path(row['directory']) / path).resolve(strict=True)
        require(str(path) in pins and (path.is_relative_to(ROOT) or path.is_relative_to(LLAMA)), 'Foreign/unpinned compile unit')
        flags = row.get('arguments') or shlex.split(row['command'])
        driver = Path(flags[0])
        require(driver.is_absolute() and driver.name in ('riscv64-linux-gcc', 'riscv64-linux-g++') and
                str(driver.resolve(strict=True)) in pins, 'Foreign/unpinned compiler')
        if path in required:
            require(path not in observed, 'Duplicate compile unit')
            observed[path] = flags
    require(set(observed) == required, 'Missing model/native compile units')
    test_flags = observed[HERE / 'test.cpp']
    require('-UNDEBUG' in test_flags and all(i < test_flags.index('-UNDEBUG') for i, flag in enumerate(test_flags)
                                          if flag.startswith('-DNDEBUG')), 'Assertions disabled')
    for name in ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp'):
        require('-DGGML_USE_RISCV_QUANT_KV' in observed[arch / name], 'Native dispatch not compiled')
    for source in (HERE / 'test.cpp', arch / 'quant-kv.cpp',
                   ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'):
        flags = observed[source]
        fp = [f for f in flags if f in ('-ffast-math', '-fno-fast-math', '-Ofast')]
        contraction = [f for f in flags if f.startswith('-ffp-contract=')]
        require(fp and fp[-1] == '-fno-fast-math' and contraction and
                contraction[-1] == ('-ffp-contract=off' if source == HERE / 'test.cpp' else '-ffp-contract=fast'),
                'Production/test FP flags differ')
    cache = dict(line.split('=', 1) for line in (build / 'CMakeCache.txt').read_text().splitlines()
                 if '=' in line and not line.startswith(('#', '//')))
    for key, wanted in (('LLAMA_SOURCE_DIR:PATH', str(LLAMA)),
                        ('GGML_RISCV_QBS_RUNTIME_DIR:PATH', str(ROOT / 'software/qbs')),
                        ('GGML_RISCV_AKV_RUNTIME_DIR:PATH', str(ROOT / 'software/akv')),
                        ('GGML_RISCV_AKV_QUANT_KV:BOOL', 'ON'), ('GGML_RISCV_QBS:BOOL', 'ON'),
                        ('GGML_RVV:BOOL', 'ON')):
        require(cache.get(key) == wanted, 'Wrong CMake cache: ' + key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prerequisite', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    require(1 <= args.timeout <= 7200, 'QEMU timeout must be 1..7200')
    out, build, gate = args.output.resolve(), args.build.resolve(), args.prerequisite.resolve(strict=True)
    require(all(p.is_relative_to(ROOT / 'verification/out') for p in (out, build, gate)), 'Use verification/out')
    require(not out.exists() and not build.exists(), 'Fresh build and result directories required')
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a) for a, b in ((out, build), (out, gate), (build, gate))),
            'Separate graph/build/output required')
    require(not any(c.isspace() for c in str(out) + str(build)), 'Initramfs paths cannot contain whitespace')
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None, prerequisite=str(gate), build=str(build))
    env = dict(HOME=os.environ.get('HOME', '/home/wangwy'), PATH=str(PLATFORM / 'tools/bin') + ':/usr/bin:/bin',
               LANG='C', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')

    def save():
        atomic_json(out / 'status.json', state)

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)

    def run(argv, name, timeout):
        def started(pid):
            state.update(state=name.upper(), child_pid=pid)
            save()
        atomic_json(out / (name + '.command.json'), list(map(str, argv)))
        try:
            require(run_command(list(map(str, argv)), out / (name + '.log'), timeout, env, started) == 0, name + ' failed')
        finally:
            state['child_pid'] = None
            save()

    save()
    try:
        pins = prerequisite(gate)
        external = model_inputs()
        require(all(name not in pins or pins[name] == sha for name, sha in external.items()), 'Graph/model source mismatch')
        pins.update(external)
        sources = set(verify_native_build(QEMU))
        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        compiler = PLATFORM / 'tools/bin/riscv64-linux-gcc'
        sources.update({MODEL, DISK, TOOLCHAIN, QEMU, cpio, compiler.resolve(strict=True),
                        PLATFORM / 'images/Image', PLATFORM / 'images/fw_dynamic.bin', LEGACY / 'model_live/init.c',
                        Path('/usr/sbin/debugfs'), Path('/usr/bin/timeout'), Path('/usr/bin/cmake'),
                        Path('/usr/bin/make'), Path('/usr/bin/rg'), Path(sys.executable).resolve()})
        for name in ('riscv64-linux-gcc', 'riscv64-linux-g++'):
            for directory in (PLATFORM / 'tools/bin', Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin')):
                sources.add((directory / name).resolve(strict=True))
        for directory in (ROOT / 'software/qbs', ROOT / 'software/akv', HERE):
            sources.update(p for p in directory.rglob('*') if p.is_file() and
                           (p.suffix.lower() in {'.c', '.cc', '.cpp', '.h', '.hpp', '.s', '.cmake', '.in', '.py', '.json', '.md'}
                            or p.name == 'CMakeLists.txt'))
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name and Path(name).resolve().is_relative_to(ROOT):
                sources.add(Path(name).resolve())
        collected = hashes(sources)
        require(all(name not in pins or pins[name] == sha for name, sha in collected.items()), 'Prerequisite/current source mismatch')
        pins.update(collected)
        atomic_json(out / 'environment.json', env)
        pins.update(hashes([out / 'environment.json']))
        atomic_json(out / 'source-pins.json', pins)

        def unchanged():
            check_pins(pins)
            require(model_inputs() == external, 'Model external inventory changed')

        unchanged()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_OK', launched=False, source_pins_sha256=digest(out / 'source-pins.json'))
            atomic_json(out / 'result.json', result)
            state.update(state='PREFLIGHT_OK', result=result)
            return
        run(['/usr/bin/cmake', '-S', HERE, '-B', build, '-DLLAMA_SOURCE_DIR=' + str(LLAMA),
             '-DCMAKE_TOOLCHAIN_FILE=' + str(TOOLCHAIN), '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_EXE_LINKER_FLAGS=-static'], 'configure', 180)
        check_compile_sources(build, pins)
        run(['/usr/bin/cmake', '--build', build, '--target', TARGET, '-j16'], 'build', 1800)
        check_compile_sources(build, pins)
        unchanged()
        argv = ['/usr/bin/timeout', '-k', '10', '180', '/usr/sbin/debugfs', '-R', 'cat ' + MODEL_PATH, str(DISK)]
        atomic_json(out / 'disk-model.command.json', argv)
        with (out / 'disk-model.log').open('xb') as log:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=log, env=env, start_new_session=True)
            state.update(state='CHECKING_MODEL_DISK', child_pid=process.pid)
            save()
            value, length = hashlib.sha256(), 0
            try:
                for chunk in iter(lambda: process.stdout.read(4 * 1024 * 1024), b''):
                    value.update(chunk)
                    length += len(chunk)
                require(process.wait(timeout=10) == 0, 'Cannot read guest model')
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                process.stdout.close()
                state['child_pid'] = None
                save()
        require(length == MODEL.stat().st_size and value.hexdigest() == pins[str(MODEL)], 'Guest GGUF differs from host')
        atomic_json(out / 'model-identity.json', dict(host=str(MODEL), guest=MODEL_PATH, bytes=length,
                    sha256=value.hexdigest(), disk=str(DISK), disk_sha256=pins[str(DISK)]))
        run([compiler, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', LEGACY / 'model_live/init.c',
             '-o', out / 'init'], 'init-build', 120)
        binary, listing = build / TARGET, out / 'initramfs.list'
        require(binary.is_file(), 'Missing model ELF')
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\n'
                           f'file /init {out / "init"} 755 0 0\nfile /test {binary} 755 0 0\n')
        with (out / 'initramfs.cpio').open('xb') as dest, (out / 'cpio.log').open('xb') as log:
            subprocess.run([cpio, listing], stdout=dest, stderr=log, env=env, check=True, timeout=60)
        pins.update(hashes([binary, build / 'CMakeCache.txt', build / 'compile_commands.json',
                           out / 'init', listing, out / 'initramfs.cpio', out / 'model-identity.json']))
        atomic_json(out / 'source-pins.json', pins)
        unchanged()
        run([QEMU, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp', '1', '-m', '4G', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
             '-bios', PLATFORM / 'images/fw_dynamic.bin', '-kernel', PLATFORM / 'images/Image',
             '-initrd', out / 'initramfs.cpio', '-drive', f'file={DISK},if=virtio,format=raw,readonly=on',
             '-append', 'console=ttyS0 rdinit=/init'], 'qemu', args.timeout)
        checked = check_log((out / 'qemu.log').read_text())
        unchanged()
        verify_native_build(QEMU)
        checked.update(state='PASS', current_inputs_match=True, log_sha256=digest(out / 'qemu.log'),
                       source_pins_sha256=digest(out / 'source-pins.json'), elf_sha256=digest(binary),
                       model_sha256=value.hexdigest(), prerequisite_result_sha256=digest(gate / 'result.json'))
        atomic_json(out / 'result.json', checked)
        state.update(state='PASS', result=checked)
    except BaseException as exc:
        state.update(state='INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL', error=repr(exc))
        atomic_json(out / 'result.json', dict(state=state['state'], error=repr(exc)))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
