#!/usr/bin/env python3
"""Bounded successor GGML paired functional worker; no RTL/performance claim."""
import argparse
import hashlib
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
sys.path.insert(0, str(LEGACY))
from run_live_graph import digest, hashes, atomic_json, run_command, verify_native_build
from capture_host import validate_capture
from check import check_log, require

LLAMA = Path('/home/wangwy/llama/llama.cpp')
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
CAPTURE = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
QEMU = ROOT / 'verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64'
TOOLCHAIN = Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')
TARGET = 'ggml-quant-kv-grouped-pv'


def external_inputs(llama=LLAMA, snapshot=HERE / 'external_snapshot.json'):
    manifest = json.loads(snapshot.read_text())
    require(manifest['schema'] == 1 and manifest['source'] == str(llama), 'Snapshot source mismatch')
    listing = subprocess.run(['/usr/bin/rg', '--files', 'ggml', 'cmake'], cwd=llama,
                             env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                             check=True, capture_output=True, text=True, timeout=30).stdout.splitlines()
    require(listing and len(listing) == len(set(listing)), 'Invalid external inventory')
    pins = {}
    rows = []
    for name in sorted(listing):
        path = llama / name
        require(path.resolve(strict=True).is_relative_to(llama), 'External source escapes tree')
        sha = digest(path)
        pins[str(path)] = sha
        rows.append(f'{sha}  {name}\n')
    actual = hashlib.sha256(''.join(rows).encode()).hexdigest()
    require(actual == manifest['tree_sha256'], 'Reviewed external tree differs from successor snapshot')
    require(all(pins.get(str(llama / name)) == sha for name, sha in manifest['source_sha256'].items()),
            'Reviewed external key source differs')
    return pins


def check_compile_sources(build, llama=LLAMA):
    required = {llama / 'ggml/src/ggml-cpu/arch/riscv' / name for name in
                ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp')}
    runtime = ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'
    required.update({HERE / 'test.cpp', runtime})
    observed = {}
    for row in json.loads((build / 'compile_commands.json').read_text()):
        source = Path(row['file'])
        source = (source if source.is_absolute() else Path(row['directory']) / source).resolve(strict=True)
        require(source.is_relative_to(llama) or source.is_relative_to(ROOT), 'Foreign compile source')
        if source in required:
            require(source not in observed, 'Ambiguous duplicate compile unit')
            observed[source] = row.get('arguments') or shlex.split(row['command'])
    require(set(observed) == required, 'Missing native compile units')
    for source, flags in observed.items():
        require(any(flag.startswith('-march=rv64gcv') for flag in flags), 'RVV target not compiled')
        fp = [flag for flag in flags if flag in ('-ffast-math', '-fno-fast-math', '-Ofast')]
        require(not fp or fp[-1] == '-fno-fast-math', 'Unsafe FP option enabled')
        if source.name == 'quant-kv.cpp' or source == runtime or source == HERE / 'test.cpp':
            require(fp and fp[-1] == '-fno-fast-math', 'Strict FP option missing')
        if source.name in ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp'):
            require('-DGGML_USE_RISCV_QUANT_KV' in flags, 'Quantized dispatch not compiled')
        if source.name == 'quant-kv.cpp' or source == runtime:
            contract = [flag for flag in flags if flag.startswith('-ffp-contract=')]
            require(contract and contract[-1] == '-ffp-contract=fast', 'Production recurrence flags differ')
    flags = observed[HERE / 'test.cpp']
    require('-UNDEBUG' in flags and all(i < flags.index('-UNDEBUG') for i, flag in enumerate(flags)
                                      if flag.startswith('-DNDEBUG')), 'Assertions disabled')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    require(1 <= args.jobs <= 32, 'Jobs must be 1..32')
    out, build = args.output.resolve(), args.build.resolve()
    require(out.is_relative_to(ROOT / 'verification/out') and build.is_relative_to(ROOT / 'verification/out'),
            'Use independent verification/out directories')
    require(not out.is_relative_to(build) and not build.is_relative_to(out), 'Separate output and build required')
    require(not out.exists() and not build.exists(), 'Fresh build and result directories required')
    require(not any(c.isspace() for c in str(out) + str(build)), 'Initramfs paths cannot contain whitespace')
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None, build=str(build),
                 whole_model=False, rtl_performance=False)
    environment = dict(HOME=os.environ.get('HOME', '/home/wangwy'),
                       PATH=str(PLATFORM / 'tools/bin') + ':/usr/bin:/bin',
                       LANG='C', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')

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
            code = run_command(list(map(str, argv)), out / (name + '.log'), timeout, environment, started)
            require(code == 0, name + ' failed: ' + str(code))
        finally:
            state['child_pid'] = None
            save()

    save()
    try:
        pins = external_inputs()
        sources = set(verify_native_build(QEMU))
        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        sources.update({TOOLCHAIN, QEMU, PLATFORM / 'images/Image', PLATFORM / 'images/fw_dynamic.bin',
                        LEGACY / 'ggml_live/init.c', LEGACY / 'run_live_graph.py',
                        LEGACY / 'capture_host.py', LEGACY / 'layout.py',
                        ROOT / 'verification/qbs/run_ggml_segmented.py',
                        ROOT / 'verification/qbs/run_half_scale_soc.py',
                        ROOT / 'verification/qbs/run_tile_context_engine.py',
                        Path('/usr/bin/cmake'), Path('/usr/bin/rg'), Path(sys.executable).resolve(), cpio,
                        CAPTURE / 'result.json', CAPTURE / 'source-pins.json'})
        for name in ('riscv64-linux-gcc', 'riscv64-linux-g++'):
            sources.add((PLATFORM / 'tools/bin' / name).resolve(strict=True))
        for directory in (ROOT / 'software/qbs', ROOT / 'software/akv', HERE):
            sources.update(p for p in directory.rglob('*') if p.is_file() and
                           (p.suffix in {'.c', '.cpp', '.h', '.hpp', '.S', '.cmake', '.in', '.py', '.json', '.md'}
                            or p.name == 'CMakeLists.txt'))
        receipt = json.loads((CAPTURE / 'result.json').read_text())
        require(receipt['state'] == 'REAL_HOST_QUANTIZED_KV_CAPTURED' and
                digest(CAPTURE / 'source-pins.json') == receipt['source_pins_sha256'],
                'Capture receipt/pins mismatch')
        for kind in ('q8_0', 'q4_0'):
            checked = validate_capture(CAPTURE / ('capture-k-' + kind + '-v-q8_0'), kind)
            require(checked == receipt['captures'][kind], 'Real capture changed')
            sources.update(Path(p) for p in checked['file_sha256'])
        pins.update(hashes(sources))
        atomic_json(out / 'environment.json', environment)
        pins.update(hashes([out / 'environment.json']))
        atomic_json(out / 'source-pins.json', pins)

        def unchanged():
            require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Paired graph input drift')
            require(external_inputs() == {p: sha for p, sha in pins.items() if Path(p).is_relative_to(LLAMA)},
                    'External inventory changed')

        unchanged()
        if args.preflight_only:
            result = dict(state='PREFLIGHT_OK', launched=False, input_count=len(pins),
                          source_pins_sha256=digest(out / 'source-pins.json'), rtl_performance=False)
            atomic_json(out / 'result.json', result)
            state.update(state='PREFLIGHT_OK', result=result)
            return
        run(['/usr/bin/cmake', '-S', HERE, '-B', build, '-DLLAMA_SOURCE_DIR=' + str(LLAMA),
             '-DCMAKE_TOOLCHAIN_FILE=' + str(TOOLCHAIN), '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_EXE_LINKER_FLAGS=-static'], 'configure', 180)
        check_compile_sources(build)
        unchanged()
        run(['/usr/bin/cmake', '--build', build, '--target', TARGET, '-j' + str(args.jobs)], 'build', 1800)
        unchanged()
        binary = build / TARGET
        require(binary.is_file(), 'Missing paired graph ELF')
        run([PLATFORM / 'tools/bin/riscv64-linux-gcc', '-march=rv64gc', '-mabi=lp64d', '-O2', '-static',
             LEGACY / 'ggml_live/init.c', '-o', out / 'init'], 'init-build', 120)
        listing = ['dir /dev 755 0 0', 'nod /dev/console 600 0 0 c 5 1',
                   f'file /init {out / "init"} 755 0 0', f'file /test {binary} 755 0 0']
        for kind, label in (('q8_0', 'q8'), ('q4_0', 'q4')):
            listing.append(f'dir /{label} 755 0 0')
            directory = CAPTURE / ('capture-k-' + kind + '-v-q8_0') / 'decode/block'
            for name in ('attn_q_input-0.bin', 'attn_k_input-0.bin', 'attn_v_input-0.bin',
                         'attn_mask_input-0.bin', 'kqv_out-0.bin'):
                listing.append(f'file /{label}/{name} {directory / name} 644 0 0')
        listing_path = out / 'initramfs.list'
        listing_path.write_text('\n'.join(listing) + '\n')
        with (out / 'initramfs.cpio').open('wb') as target, (out / 'cpio.log').open('wb') as log:
            subprocess.run([cpio, listing_path], stdout=target, stderr=log, env=environment, check=True, timeout=60)
        pins.update(hashes([binary, build / 'CMakeCache.txt', build / 'compile_commands.json',
                           out / 'init', listing_path, out / 'initramfs.cpio']))
        atomic_json(out / 'source-pins.json', pins)
        unchanged()
        run([QEMU, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
             '-bios', PLATFORM / 'images/fw_dynamic.bin', '-kernel', PLATFORM / 'images/Image',
             '-initrd', out / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'], 'qemu', 900)
        result = check_log((out / 'qemu.log').read_text().replace('\r\n', '\n'))
        unchanged()
        verify_native_build(QEMU)
        result.update(state='PASS', current_inputs_match=True, log_sha256=digest(out / 'qemu.log'),
                      source_pins_sha256=digest(out / 'source-pins.json'), elf_sha256=digest(binary))
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
