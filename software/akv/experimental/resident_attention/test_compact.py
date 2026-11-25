#!/usr/bin/env python3
"""Execute real RVV preparation in Spike and softmax differential in QEMU.

The custom PV instruction is replaced by a source-register capture, not by an
arithmetic emulation. This checks its inputs, NOT custom compute or RTL timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
OLD = OUT / 'resident_direct_build_preflight_20261113_02/inputs/sdk/software/akv'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
CC = PLATFORM / 'tools/bin/riscv64-linux-gcc'
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
QEMU = OUT / 'stage5_qemu_build_20261110_07/qemu-system-riscv64'
CAPTURE = OUT / 'resident_pv_prepare_vcs_20261109_01/work/run.vcs.log'
OVERLAY = ['include/akv/akv.h', 'src/akv_v2_native_riscv.c',
           'experimental/resident_attention/pv_compact.h',
           'experimental/resident_attention/pv_compact.S']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    out = ap.parse_args().output.resolve()
    require(out.parent == OUT and out.name.startswith('resident_compact_'), 'independent signoff output required')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins, commands = {}, []
    report = dict(state='FAIL', rtl_executed=False, board_executed=False,
                  custom_compute_executed=False, performance_measured=False)

    def pin(p):
        digest = sha(p)
        require(str(p) not in pins or pins[str(p)] == digest,
                'input changed between checkpoints: ' + str(p))
        pins[str(p)] = digest

    def run(label, argv, timeout=120):
        argv = list(map(str, argv))
        with (out / (label + '.log')).open('x') as stream:
            p = subprocess.run(argv, cwd=out, stdin=subprocess.DEVNULL,
                               stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        commands.append(dict(label=label, argv=argv, returncode=p.returncode))
        require(p.returncode == 0, label + ' failed')
        return (out / (label + '.log')).read_text()

    try:
        for p in (Path(__file__).resolve(), HERE / 'test_compact.c', CAPTURE, SPIKE, QEMU, CC.resolve()):
            pin(p)
        shutil.copyfile(__file__, inputs / 'test_compact.py')
        shutil.copytree(OLD, inputs / 'old')
        shutil.copytree(OLD, inputs / 'new')
        for rel in OVERLAY:
            src = ROOT / 'software/akv' / rel
            pin(src)
            shutil.copyfile(src, inputs / 'new' / rel)
        # Both numerical wrappers expose the same C workspace type. Probe the
        # archived pre-union ABI separately, without exchanging struct objects.
        shutil.copyfile(inputs / 'new/include/akv/akv.h', inputs / 'old/include/akv/akv.h')
        for p in OLD.rglob('*'):
            if p.is_file(): pin(p)
        shutil.copyfile(HERE / 'test_compact.c', inputs / 'test.c')
        captures = {}
        for cid, kind, bits in re.findall(
                r'^PV_PREP_DATA id=([012]) kind=(probability|seed|scale) bits=([0-9a-f]+)$',
                CAPTURE.read_text(), re.M):
            key = (int(cid), kind)
            require(key not in captures, 'duplicate capture')
            width = 4 if kind == 'seed' else 8
            captures[key] = [int(bits[i:i+width], 16) for i in range(0, len(bits), width)]
        header = []
        for kind, n, ctype in [('probability', 128, 'uint32_t'), ('scale', 2, 'uint32_t'), ('seed', 256, 'uint16_t')]:
            require(all(len(captures[i, kind]) == n for i in range(3)), 'capture shape')
            header.append('static const %s capture_%s[3][%d] = {' % (ctype, kind, n))
            header += ['{' + ','.join(hex(v) for v in captures[i, kind]) + '},' for i in range(3)]
            header.append('};')
        (inputs / 'captures.h').write_text('\n'.join(header) + '\n')

        # Capture the actual leaf's register inputs at precisely the issue site.
        # Do not execute its output stores, invent custom arithmetic or omit FP work.
        def capture(control):
            return '''    li t0,128
    vsetvli zero,t0,e16,m2,ta,ma
    vse16.v v8,(a7)
    addi a7,a7,256
    vse16.v v10,(a7)
    addi a7,a7,256
    vse16.v v12,(a7)
    addi a7,a7,256
    sd %s,0(a7)
    ret
''' % control
        text = (inputs / 'old/experimental/resident_attention/pv_prepare.S').read_text()
        require(text.count('    ret') == 1, 'old capture insertion')
        (inputs / 'capture_old.S').write_text(text.replace('resident_pv_prepare', 'capture_old')
                                            .replace('    ret', capture('a6')))
        text = (inputs / 'new/experimental/resident_attention/pv_compact.S').read_text()
        require(text.count('    .word           0x0485705b') == 1, 'new capture insertion')
        (inputs / 'capture_new.S').write_text(text.replace('akv_experimental_resident_pv_compact', 'capture_new')
            .replace('    .word           0x0485705b', capture('a0')))

        flags = ['-O3', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-fno-fast-math',
                 '-ffp-contract=off', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                 '-ffunction-sections', '-fdata-sections', '-Wno-unknown-pragmas', '-I' + str(inputs),
                 '-I' + str(inputs / 'new/include')]
        objects = []
        layout_body = ('p[0]=sizeof(akv_attention_v2_workspace_t); p[1]=_Alignof(akv_attention_v2_workspace_t);\n' +
            ''.join('p[%d]=offsetof(akv_attention_v2_workspace_t,%s);\n' % (i+2, f)
                    for i, f in enumerate(('accumulator', 'score', 'maximum', 'sum', 'old_scale'))))
        old_layout = inputs / 'old-layout.c'
        old_layout.write_text('#include <stddef.h>\n#include "' + str(OLD / 'include/akv/akv.h') +
                              '"\nvoid old_layout(size_t *p) {\n' + layout_body + '}\n')
        run('old-layout-build', [CC, *flags, '-c', old_layout, '-o', out / 'old-layout.o'])
        objects.append(out / 'old-layout.o')
        for variant in ('old', 'new'):
            src = inputs / (variant + '.c')
            extra = ', compact' if variant == 'new' else ''
            arg = ', unsigned compact' if variant == 'new' else ''
            src.write_text('#include <stddef.h>\n#include "' + str(inputs / variant / 'src/akv_v2_native_riscv.c') + '"\n' +
                'void ' + variant + '_softmax(const uint16_t *m,float s,akv_attention_v2_workspace_t *w,' +
                'uint32_t start,uint32_t t,uint32_t h' + arg + ') {\n' +
                ' apply_scale_mask_and_softmax(m,s,w,start,t,h,NULL' + extra + ');\n}\n' +
                ('void new_layout(size_t *p) {\n' + layout_body + '}\n' if variant == 'new' else ''))
            obj = out / (variant + '.o')
            defs = ['-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1', '-DAKV_REFILL_OVERLAP=0']
            if variant == 'new': defs += ['-DAKV_RESIDENT_COMPACT_COEFFICIENTS=1']
            run(variant + '-build', [CC, *flags, *defs, '-c', src, '-o', obj])
            symbols = run(variant + '-symbols', [CC.with_name('riscv64-linux-nm'), '--defined-only', obj])
            locals_ = [name for kind, name in re.findall(r'^\w+ ([A-Z]) (\S+)$', symbols, re.M)
                       if name not in (variant + '_softmax', variant + '_layout')]
            run(variant + '-localize', [CC.with_name('riscv64-linux-objcopy'),
                                      *['--localize-symbol=' + n for n in locals_], obj])
            objects.append(obj)
        elf = out / 'test-linux'
        run('linux-build', [CC, *flags, '-static', inputs / 'test.c',
            inputs / 'capture_old.S', inputs / 'capture_new.S', *objects,
            inputs / 'new/src/akv_features.c', '-Wl,--gc-sections', '-lm', '-o', elf])
        run('linux-disassembly', [CC.with_name('riscv64-linux-objdump'), '-d', elf])
        # RVV-only preparation also runs independently on the verification Spike.
        client = ROOT / 'verification/performance/resident_deployment'
        spike_elf = out / 'test-spike.elf'
        for name in ('client_start.S', 'client.ld', 'test_compact_memory.c'):
            pin(client / name)
        run('spike-build', [CC, *flags, '-DPREP_ONLY', '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0',
            '-fno-builtin', '-fno-stack-protector', '-ffreestanding', '-nostdlib', '-static',
            '-T' + str(client / 'client.ld'), client / 'client_start.S', inputs / 'test.c',
            inputs / 'capture_old.S', inputs / 'capture_new.S', client / 'test_compact_memory.c',
            '-Wl,--gc-sections', '-lgcc', '-o', spike_elf])
        symbols = run('spike-symbols', [CC.with_name('riscv64-linux-nm'), '-n', spike_elf])
        address = re.findall(r'^(\w+) T test_exit$', symbols, re.M)
        require(len(address) == 1, 'Spike terminal')
        debug = inputs / 'debug.cmd'
        debug.write_text('until pc 0 ' + address[0] + '\nreg 0 a0\nquit\n')
        for p in inputs.rglob('*'):
            if p.is_file(): pin(p)
        pin(spike_elf)
        pin(elf)
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        log = run('spike', [SPIKE, '-d', '--debug-cmd=' + str(debug),
            '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m4', spike_elf])
        require(re.findall(r'^0x[0-9a-f]+$', log, re.M) == ['0x0000000000000000'], 'Spike mismatch')

        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        listing = inputs / 'initramfs.list'
        listing.write_text('dir /dev 0755 0 0\nnod /dev/console 0600 0 0 c 5 1\nfile /init ' + str(elf) + ' 0755 0 0\n')
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=30)
        for p in (cpio, PLATFORM / 'images/fw_dynamic.bin', PLATFORM / 'images/Image', elf, spike_elf): pin(p)
        pin(out / 'initramfs.cpio')
        pin(listing)
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        log = run('qemu', [QEMU, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true',
            '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
            '-bios', PLATFORM / 'images/fw_dynamic.bin', '-kernel', PLATFORM / 'images/Image',
            '-initrd', out / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'])
        require('COMPACT_CHECK rc=0 prep=1838 softmax=9216 custom_compute=0' in log and 'Kernel panic' not in log,
                'QEMU differential mismatch or incomplete matrix')
        require(all(sha(p) == h for p, h in pins.items()), 'source drift')
        report.update(state='RVV_PREPARATION_AND_SOFTMAX_PASS', preparation_cases=1838,
            softmax_tile_comparisons=9216, native_workspace_and_flags_identical=True,
            compact_coefficients_statistics_and_flags_identical=True, workspace_abi_unchanged=True,
            post_pins_match=True, elf_sha256=sha(elf), spike_elf_sha256=sha(spike_elf))
    except Exception as exc:
        report['error'] = repr(exc)
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return report['state'] == 'FAIL'


if __name__ == '__main__':
    raise SystemExit(main())
