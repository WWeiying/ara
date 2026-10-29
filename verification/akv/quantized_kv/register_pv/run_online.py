#!/usr/bin/env python3
"""Independent functional-only online Attention test; no performance inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    parser.add_argument('--runtime', action='store_true',
                        help='Exercise full runtime adapter with QBS reference executor')
    parser.add_argument('--shared-runtime', action='store_true',
                        help='Use the promoted software runtime, not the frozen experiment')
    parser.add_argument('--fp-contract', choices=('off', 'fast'), default='off',
                        help='Use fast to match the production GGML runtime build')
    args = parser.parse_args()
    if args.shared_runtime and not args.runtime:
        parser.error('--shared-runtime requires --runtime')
    out = args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Fresh independent output directory required')
    out.mkdir(parents=True)
    pins, commands, trials = {}, [], []
    state = dict(state='PREPARING', functional_only=True, rtl_performance=False,
                 production_enabled=False, shared_runtime=args.shared_runtime,
                 fp_contract=args.fp_contract, trials=trials)
    env = dict(HOME='/home/wangwy', PATH='/usr/bin:/bin', LANG='C.UTF-8')

    def pin(path):
        path = Path(path).resolve(strict=True)
        value = digest(path)
        if str(path) in pins and pins[str(path)] != value:
            raise ValueError('Source drift: ' + str(path))
        pins[str(path)] = value

    def unchanged():
        for path, value in pins.items():
            if digest(path) != value:
                raise ValueError('Source drift: ' + path)

    def run(argv, name, bound=180, stdout=None):
        argv = list(map(str, argv))
        pin(argv[0]); unchanged()
        commands.append(dict(label=name, argv=argv, timeout=bound))
        save(out / 'commands.json', commands)
        state['state'] = name.upper()
        save(out / 'status.json', state)
        with (out / (name + '.log')).open('wb') as log:
            child = subprocess.Popen(argv, cwd=out, env=env,
                stdout=log if stdout is None else stdout, stderr=log,
                start_new_session=True)
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()
                raise
            if code:
                raise RuntimeError(name + ' exit=' + str(code))
        unchanged()
        return (out / (name + '.log')).read_text(errors='replace')

    try:
        cc = PLATFORM / 'tools/bin/riscv64-linux-gcc'
        init = HERE.parent / 'ggml_live/init.c'
        source = HERE / ('test_runtime.c' if args.runtime else 'test_online.c')
        sources = [source]
        if args.runtime:
            sources += [ROOT / 'software/akv/experimental/quantized_kv/register_pv/runtime.c'
                if args.shared_runtime else HERE / 'runtime_candidate.c',
                ROOT / 'software/akv/experimental/quantized_kv/runtime.c',
                ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c',
                ROOT / 'software/qbs/src/qbs_runtime.c', ROOT / 'verification/qbs/qbs_ref.c']
        for path in (Path(__file__), cc, source, init):
            pin(path)
        base = [cc, '-O3', '-static', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                '-fno-tree-vectorize', '-fno-fast-math', '-ffp-contract=' + args.fp_contract,
                '-frounding-math', '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT),
                '-I' + str(ROOT / 'software/qbs/include')]
        for program in ('cc1', 'as', 'ld'):
            pin(run([cc, '-print-prog-name=' + program], 'locate-' + program).strip())
        for library in ('libm.a', 'libc.a', 'libgcc.a', 'libgcc_eh.a'):
            pin(run([cc, '-print-file-name=' + library], 'locate-' + library).strip())
        for label, path in [(str(i), p) for i, p in enumerate(sources)] + [('init', init)]:
            deps = run([*base, '-M', '-MT', 'object', path], label + '-dependencies')
            for dep in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1]):
                pin(dep)
        run([*base, *sources, '-lm', '-o', out / 'test'], 'build')
        run([cc, '-O2', '-static', '-march=rv64gc', '-mabi=lp64d',
             init, '-o', out / 'init'], 'init-build')
        for path in (out / 'test', out / 'init'):
            pin(path)
        listing = out / 'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n' +
            f'file /init {out / "init"} 755 0 0\nfile /test {out / "test"} 755 0 0\n')
        pin(listing)
        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        with (out / 'initramfs.cpio').open('xb') as stream:
            run([cpio, listing], 'cpio', stdout=stream)
        pin(out / 'initramfs.cpio')
        qemu = ROOT / 'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
        kernel, firmware = PLATFORM / 'images/Image', PLATFORM / 'images/fw_dynamic.bin'
        for path in (qemu, kernel, firmware):
            pin(path)
        save(out / 'input-pins.json', pins)
        if args.execute_reviewed:
            markers = (
                (1024, 'REGISTER_ONLINE_PASS cases=896 exact=1 flags=1 guards=1 terminal_error=1 scalar_oracle=1 rounding_reject=1'),
                (256, 'REGISTER_ONLINE_UNSUPPORTED_VLEN_PASS no_effects=1'))
            prefix = 'REGISTER_ONLINE_'
            if args.runtime:
                markers = (
                    (1024, 'REGISTER_RUNTIME_PASS cases=288 exact=1 flags=1 panels=1 failure_no_retry=1'),
                    (256, 'REGISTER_RUNTIME_UNSUPPORTED_VLEN_PASS no_effects=1'))
                prefix = 'REGISTER_RUNTIME_'
            for vlen, marker in markers:
                name = 'qemu-vlen' + str(vlen)
                text = run([qemu, '-M', 'virt', '-cpu',
                    f'rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true',
                    '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none',
                    '-serial', 'stdio', '-bios', firmware, '-kernel', kernel,
                    '-initrd', out / 'initramfs.cpio',
                    '-append', 'console=ttyS0 rdinit=/init'], name, 600)
                lines = text.replace('\r\n', '\n').splitlines()
                if ([line for line in lines if line.startswith(prefix)] != [marker]
                    or lines.count('GUEST_TEST_EXIT=0') != 1
                    or any('Kernel panic' in line for line in lines)):
                    raise ValueError('Numerical/guest completion mismatch: ' + name)
                trials.append(dict(vlen=vlen, marker=marker,
                                   log_sha256=digest(out / (name + '.log'))))
            state['state'] = 'PASS'
        else:
            state['state'] = 'BUILT_NOT_EXECUTED'
        unchanged()
        state.update(source_pre_post_match=True, elf_sha256=digest(out / 'test'),
                     input_pins_sha256=digest(out / 'input-pins.json'))
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        save(out / 'result.json', state)
        save(out / 'status.json', state)


if __name__ == '__main__':
    main()
