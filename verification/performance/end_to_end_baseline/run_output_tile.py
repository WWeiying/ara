#!/usr/bin/env python3
"""Bounded QEMU arithmetic/CSR test of an RVV output-tile leaf or schedule."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=('leaf', 'online', 'runtime', 'entry'), default='leaf')
    parser.add_argument('--verification', type=Path,
                        default=Path('/home/wangwy/openproject/ara_dsa_signoff_integration'))
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(args.verification.resolve() / 'verification/out'),
            'Use the sole verification worktree output area')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    report = dict(state='INCOMPLETE', suite=args.suite, functional_only=True, rtl_performance=False,
                  production_enabled=False, trials=[])

    def pin(path):
        path = Path(path).resolve(strict=True)
        current = digest(path)
        require(str(path) not in pins or pins[str(path)] == current, 'Source drift')
        pins[str(path)] = current

    def run(argv, name, timeout=120, binary_output=None):
        argv = list(map(str, argv))
        pin(argv[0])
        commands.append(dict(name=name, argv=argv, timeout=timeout))
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result = subprocess.run(argv, cwd=out, capture_output=True, timeout=timeout)
        (out / (name+'.log')).write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, name+' failed; see log')
        if binary_output:
            binary_output.write_bytes(result.stdout)
        return result.stdout.decode(errors='replace')

    try:
        cc = PLATFORM / 'tools/bin/riscv64-linux-gcc'
        source = HERE / ('test_output_tile.c' if args.suite=='leaf' else 'test_output_'+args.suite+'.c')
        sources = [source]
        if args.suite in ('runtime', 'entry'):
            sources += [ROOT/'software/akv/experimental/quantized_kv/output_tile/runtime.c',
                        ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                        ROOT/'software/akv/experimental/quantized_kv/runtime_strided.c',
                        ROOT/'software/qbs/src/qbs_runtime.c', ROOT/'verification/qbs/qbs_ref.c']
        init = ROOT / 'verification/akv/quantized_kv/ggml_live/init.c'
        for path in (Path(__file__), HERE/'audit.py', source, init):
            pin(path)
        base = [cc, '-O3', '-static', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                '-fno-tree-vectorize', '-fno-fast-math', '-ffp-contract=fast',
                '-frounding-math', '-Wall', '-Wextra', '-Werror', '-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include')]
        for name in ('cc1', 'as', 'ld'):
            pin(run([cc, '-print-prog-name='+name], 'locate-'+name).strip())
        for name in ('libm.a', 'libc.a', 'libgcc.a', 'libgcc_eh.a'):
            pin(run([cc, '-print-file-name='+name], 'locate-'+name).strip())
        for label, path in [*[(f'test-{i}', s) for i,s in enumerate(sources)], ('init', init)]:
            deps = run([*base, '-M', '-MT', 'object', path], label+'-deps')
            for dep in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1]):
                pin(dep)
        archive = args.verification/'verification/out'
        capture_audit = archive/'quant-prefill-capture-audit-20261028-01'
        pin(capture_audit/'result.json'); pin(capture_audit/'manifest.json')
        require(json.loads((capture_audit/'result.json').read_text())['state']=='PASS',
                'Real capture audit was not accepted')
        captured = json.loads((capture_audit/'manifest.json').read_text())
        assembly = ['.section .rodata,"a",@progbits']
        for kind in ('q4_0', 'q8_0'):
            data = archive/'quant-prefill-capture-20261028-01'/kind/'prefill/block/attn_v_input-0.bin'
            require(captured.get(str(data)) == digest(data), 'Real V capture changed')
            require(data.stat().st_size == 136*256*8, 'Unexpected real V shape')
            pin(data)
            symbol = 'real_'+kind[:2]+'_value'
            assembly += ['.balign 64', '.global '+symbol, symbol+':', f'.incbin "{data}"']
        (out/'data.S').write_text('\n'.join(assembly)+'\n'); pin(out/'data.S')
        run([*base, *sources, out/'data.S', '-lm', '-o', out/'test'], 'build')
        pin(out/'test')
        run([cc.with_name('riscv64-linux-objdump'), '-d', out/'test'], 'disassembly')
        run([cc, '-O2', '-static', '-march=rv64gc', '-mabi=lp64d', init,
             '-o', out/'init'], 'build-init')
        pin(out/'init')
        listing = 'dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
        listing += f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n'
        (out/'initramfs.list').write_text(listing); pin(out/'initramfs.list')
        cpio = PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        run([cpio, out/'initramfs.list'], 'cpio', binary_output=out/'initramfs.cpio')
        pin(out/'initramfs.cpio')
        qemu = archive/'qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
        kernel, firmware = PLATFORM/'images/Image', PLATFORM/'images/fw_dynamic.bin'
        for path in (qemu, kernel, firmware):
            pin(path)
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        verify_pins(pins)
        markers = {
            1024: 'OUTPUT_TILE_PASS cases=1472 real=32 rejected=15 unaligned=3 exact=1 flags=1 scalar_oracle=1',
            256: 'OUTPUT_TILE_UNSUPPORTED_PASS no_effects=1',
        }
        if args.suite=='online':
            markers = {
                1024: 'OUTPUT_ONLINE_PASS cases=752 real=32 rejected=17 callback_failures=6 exact=1 flags=1',
                256: 'OUTPUT_ONLINE_UNSUPPORTED_PASS no_effects=1',
            }
        prefix = 'OUTPUT_TILE_' if args.suite=='leaf' else 'OUTPUT_ONLINE_'
        if args.suite=='runtime':
            prefix='REGISTER_RUNTIME_'
            markers={
                1024:'REGISTER_RUNTIME_PASS cases=288 exact=1 flags=1 panels=1 failure_no_retry=1',
                256:'REGISTER_RUNTIME_UNSUPPORTED_VLEN_PASS no_effects=1',
            }
        elif args.suite=='entry':
            prefix='REGISTER_GUARD_'
            markers={
                1024:'REGISTER_GUARD_PASS vlen=1024 cases=28 no_effects=1 csr_preserved=1',
                256:'REGISTER_GUARD_PASS vlen=256 cases=30 no_effects=1 csr_preserved=1',
            }
        for vlen, marker in markers.items():
            text = run([qemu, '-M', 'virt', '-cpu',
                f'rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true',
                '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none',
                '-serial', 'stdio', '-bios', firmware, '-kernel', kernel,
                '-initrd', out/'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'],
                'qemu-'+str(vlen), timeout=180).replace('\r', '')
            lines = text.splitlines()
            require([line for line in lines if line.startswith(prefix)] == [marker]
                    and lines.count('GUEST_TEST_EXIT=0') == 1 and 'Kernel panic' not in text,
                    'Arithmetic/CSR/guest check failed')
            report['trials'].append(dict(vlen=vlen, marker=marker,
                log_sha256=digest(out/('qemu-'+str(vlen)+'.log'))))
        verify_pins(pins)
        state = ('LEAF_FUNCTIONAL_PASS_NOT_ONLINE_OR_RTL_ACCEPTED' if args.suite=='leaf'
                 else 'SCHEDULE_FUNCTIONAL_PASS_NOT_QK_OR_RTL_ACCEPTED')
        if args.suite in ('runtime', 'entry'):
            state='RUNTIME_REFERENCE_PASS_NOT_NATIVE_OR_MODEL_ACCEPTED'
        report.update(state=state,
                      elf_sha256=digest(out/'test'), source_pins_sha256=digest(out/'source-pins.json'))
    except Exception as exc:
        report.update(state='FAIL', error=repr(exc))
        raise
    finally:
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
        print(report['state'])


if __name__ == '__main__':
    main()
