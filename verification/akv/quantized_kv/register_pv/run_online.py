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
    parser.add_argument('--entry-guards', action='store_true',
                        help='Check actual rounding/vstart/VLEN rejection without effects')
    parser.add_argument('--early-guard-candidate', action='store_true',
                        help='Test the successor entry guard before vectorized libc')
    parser.add_argument('--prefill-prefix', action='store_true',
                        help='Test the isolated causal Prefill register-PV schedule')
    parser.add_argument('--group-sums', action='store_true',
                        help='Test isolated QBS M4 activation group sums')
    parser.add_argument('--m4-quantizer', action='store_true',
                        help='Check complete Q8_K M4 quantization on real activations')
    parser.add_argument('--fp-contract', choices=('off', 'fast'), default='off',
                        help='Use fast to match the production GGML runtime build')
    args = parser.parse_args()
    if args.m4_quantizer and (args.group_sums or args.prefill_prefix or args.runtime or args.entry_guards or args.shared_runtime or args.early_guard_candidate):
        parser.error('--m4-quantizer is a standalone quantizer experiment')
    if args.group_sums and (args.prefill_prefix or args.runtime or args.entry_guards or args.shared_runtime or args.early_guard_candidate):
        parser.error('--group-sums is a standalone arithmetic experiment')
    if args.prefill_prefix and (args.runtime or args.entry_guards or args.shared_runtime or args.early_guard_candidate):
        parser.error('--prefill-prefix is a standalone schedule experiment')
    if args.shared_runtime and not args.runtime:
        parser.error('--shared-runtime requires --runtime')
    if args.entry_guards and not (args.runtime and args.shared_runtime):
        parser.error('--entry-guards requires --runtime --shared-runtime')
    if args.early_guard_candidate and not (args.runtime and args.shared_runtime):
        parser.error('--early-guard-candidate requires --runtime --shared-runtime')
    out = args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Fresh independent output directory required')
    out.mkdir(parents=True)
    pins, commands, trials = {}, [], []
    state = dict(state='PREPARING', functional_only=True, rtl_performance=False,
                 production_enabled=False, shared_runtime=args.shared_runtime,
                 entry_guards=args.entry_guards,
                 early_guard_candidate=args.early_guard_candidate,
                 prefill_prefix=args.prefill_prefix,
                 group_sums=args.group_sums,
                 m4_quantizer=args.m4_quantizer,
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
        init_cc=cc
        link_libraries=[]
        if args.m4_quantizer:
            cc=PLATFORM/'tools/bin/riscv64-linux-g++'
        init = HERE.parent / 'ggml_live/init.c'
        source = HERE / ('test_runtime.c' if args.runtime else 'test_online.c')
        if args.entry_guards:
            source = HERE / 'test_entry_guards.c'
        if args.prefill_prefix:
            source = HERE / 'test_prefill_prefix.c'
        if args.group_sums:
            source = ROOT / 'verification/qbs/m4_group_sums/test.c'
        if args.m4_quantizer:
            source = ROOT / 'verification/qbs/m4_group_sums/test_quantizer.cpp'
        sources = [source]
        if args.runtime:
            sources += [HERE / 'runtime_entry_guard_candidate.c' if args.early_guard_candidate else
                ROOT / 'software/akv/experimental/quantized_kv/register_pv/entry.c'
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
        if args.m4_quantizer:
            ggml=Path('/home/wangwy/llama/llama.cpp/ggml')
            base+=['-isystem'+str(p) for p in (ggml/'include',ggml/'src',
                ggml/'src/ggml-cpu',ggml/'src/ggml-cpu/arch/riscv')]
            libraries=ROOT/'verification/out/register-pv-final-models-20261028-01/libraries'
            report=json.loads((libraries/'result.json').read_text())
            if report['state']!='PASS':raise ValueError('Unaccepted GGML libraries')
            pin(libraries/'result.json')
            for path,expected in report['configurations']['ON']['libraries'].items():
                if digest(path)!=expected:raise ValueError('Library drift: '+path)
                pin(path)
            directory=libraries/'on/ggml/src'
            link_libraries=['-Wl,--start-group',*[str(directory/name) for name in
                ('libggml.a','libggml-cpu.a','libggml-base.a')],'-Wl,--end-group','-ldl','-pthread']
            capture=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight/activation_f32.bin')
            archived=ROOT/'verification/out/m4-packed-qkv-build-20261027-01/manifest.json'
            pin(archived)
            expected=json.loads(archived.read_text())[str(capture)]
            if digest(capture)!=expected or capture.stat().st_size!=92160:
                raise ValueError('Real activation identity')
            pin(capture)
        for program in ('cc1', 'as', 'ld'):
            pin(run([cc, '-print-prog-name=' + program], 'locate-' + program).strip())
        for library in ('libm.a', 'libc.a', 'libgcc.a', 'libgcc_eh.a'):
            pin(run([cc, '-print-file-name=' + library], 'locate-' + library).strip())
        if args.m4_quantizer:
            pin(run([cc,'-print-file-name=libstdc++.a'],'locate-cxxlib').strip())
            pin(run([cc,'-print-prog-name=cc1plus'],'locate-cxxcompiler').strip())
        for label, path in [(str(i), p) for i, p in enumerate(sources)] + [('init', init)]:
            deps = run([*base, '-M', '-MT', 'object', path], label + '-dependencies')
            for dep in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1]):
                pin(dep)
        run([*base, *sources, *link_libraries, '-lm', '-o', out / 'test'], 'build')
        run([init_cc, '-O2', '-static', '-march=rv64gc', '-mabi=lp64d',
             init, '-o', out / 'init'], 'init-build')
        for path in (out / 'test', out / 'init'):
            pin(path)
        listing = out / 'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n' +
            f'file /init {out / "init"} 755 0 0\nfile /test {out / "test"} 755 0 0\n'+
            (f'file /activation.bin {capture} 644 0 0\n' if args.m4_quantizer else ''))
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
            if args.entry_guards:
                markers = (
                    (1024, 'REGISTER_GUARD_PASS vlen=1024 cases=28 no_effects=1 csr_preserved=1'),
                    (256, 'REGISTER_GUARD_PASS vlen=256 cases=30 no_effects=1 csr_preserved=1'))
                prefix = 'REGISTER_GUARD_'
            if args.prefill_prefix:
                markers = (
                    (1024, 'REGISTER_PREFIX_PASS cases=1792 exact=1 flags=1 guards=1 qk_equal=1 causal=1'),
                    (256, 'REGISTER_PREFIX_UNSUPPORTED_VLEN_PASS no_effects=1'))
                prefix = 'REGISTER_PREFIX_'
            if args.group_sums:
                markers = (
                    (1024, 'GROUP_SUMS_PASS vlen=1024 cases=256 exact=1 strided=1 csr=1'),
                    (256, 'GROUP_SUMS_PASS vlen=256 cases=128 exact=1 strided=1 csr=1'))
                prefix = 'GROUP_SUMS_'
            if args.m4_quantizer:
                marker='M4_SUMS_QUANTIZER_PASS cases=57 real=9 exact=1 flags=1 guards=1'
                markers=((1024,marker),(256,marker))
                prefix='M4_SUMS_'
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
