#!/usr/bin/env python3
"""GNU14 glibc ALiBi type/bit/FCSR probe in a short Linux QEMU boot, no model."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = Path(__file__).resolve().parent
BASE = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
OUT = BASE / 'enablement_portable_alibi_20261111_02'
BUILD = BASE / 'enablement_unified_build_20261111_01'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
ARCH = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')
CC = PLATFORM / 'tools/bin/riscv64-linux-gcc'
CXX = PLATFORM / 'tools/bin/riscv64-linux-g++'
QEMU = BASE / 'stage5_qemu_build_20261110_07/qemu-system-riscv64'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    require(not OUT.exists(), 'Preserve previous probe')
    OUT.mkdir()
    inputs = OUT / 'inputs'
    inputs.mkdir()
    pins, commands = {}, []
    result = dict(state='FAIL', model_executed=False, performance_measured=False, fpga_acceptance=False,
                  rtl_execution=False, native_glibc_math=True, native_akv_execution=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_', 'AKV_'))}
    env.update(LC_ALL='C', LANG='C')

    def pin(path):
        path = Path(path).absolute()
        value = sha(path)
        require(str(path) not in pins or pins[str(path)] == value, 'Input drift: ' + str(path))
        pins[str(path)] = value

    def copy(src, dst):
        pin(src)
        shutil.copyfile(src, dst)
        pin(dst)

    def run(label, argv, timeout=90):
        argv = list(map(str, argv))
        pin(Path(shutil.which(argv[0]) or argv[0]))
        with (OUT / (label + '.log')).open('x') as stream:
            child = subprocess.run(argv, cwd=OUT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, timeout=timeout)
        commands.append(dict(label=label, argv=argv, returncode=child.returncode))
        require(child.returncode == 0, 'Failed: ' + label)
        return (OUT / (label + '.log')).read_text()

    try:
        pin(__file__)
        copy(HERE / 'portable_alibi_probe.cpp', inputs / 'probe.cpp')
        source = ARCH / 'akv.cpp'
        pin(source)
        pin(ARCH.parent.parent / 'ops.cpp')
        text = source.read_text()
        first = text.index('static bool decode_features(')
        last = text.index('\n#endif\n\nstatic kernel_policy', first)
        (inputs / 'decode_features.inc').write_text(text[first:last] + '\n')
        pin(inputs / 'decode_features.inc')
        sdk = BUILD / 'inputs/sdk/software/akv'
        ggml = BUILD / 'inputs/llama/ggml'
        flags = ['-O2', '-static', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-fno-fast-math',
            '-ffp-contract=off', '-fno-builtin', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-ffunction-sections', '-fdata-sections', '-I' + str(inputs), '-I' + str(ggml / 'include'),
            '-I' + str(sdk / 'include')]
        for name, compiler, extra, src in (
                ('probe', CXX, ['-std=c++17'], inputs / 'probe.cpp'),
                ('features', CC, ['-std=c11'], sdk / 'src/akv_features.c'),
                ('runtime', CC, ['-std=c11'], sdk / 'src/akv_runtime.c')):
            dep = OUT / (name + '.d')
            run(name + '-deps', [compiler, *flags, *extra, '-M', '-MF', dep, src])
            for p in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                pin(p)
            run(name + '-build', [compiler, *flags, *extra, '-c', src, '-o', OUT / (name + '.o')])
        elf = OUT / 'probe'
        run('link', [CXX, *flags, OUT / 'probe.o', OUT / 'features.o', OUT / 'runtime.o',
            '-Wl,--gc-sections', '-lm', '-o', elf])
        pin(elf)
        run('symbols', [CC.with_name('riscv64-linux-nm'), '-S', '-C', elf])
        assembly = run('disassembly', [CC.with_name('riscv64-linux-objdump'), '-d', '-C', elf])
        live_math = re.search(r'<live_power\(float, unsigned int\)>:\n(.*?)(?=\n\n)', assembly, re.S)
        ggml_math = re.search(r'<ggml_power\(float, unsigned int\)>:\n(.*?)(?=\n\n)', assembly, re.S)
        require(live_math and ggml_math and '<__ieee754_pow>' in live_math[1] and
                'fcvt.d.s' in live_math[1] and 'fcvt.s.d' in live_math[1] and
                '<__ieee754_powf>' in ggml_math[1], 'Missing actual libc pow/powf call paths')
        cpio = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
        pin(cpio)
        listing = OUT / 'initramfs.list'
        listing.write_text('dir /dev 0755 0 0\nnod /dev/console 0600 0 0 c 5 1\nfile /init ' + str(elf) + ' 0755 0 0\n')
        with (OUT / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=30)
        require(sha(QEMU) == '1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a', 'QEMU identity')
        for path in (QEMU, PLATFORM / 'images/fw_dynamic.bin', PLATFORM / 'images/Image', listing, OUT / 'initramfs.cpio'):
            pin(path)
        save(OUT / 'source-pins.json', pins)
        log = run('qemu', [QEMU, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true',
            '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
            '-bios', PLATFORM / 'images/fw_dynamic.bin', '-kernel', PLATFORM / 'images/Image',
            '-initrd', OUT / 'initramfs.cpio', '-append', 'console=ttyS0 rdinit=/init'], timeout=120)
        coeff = re.findall(r'^ALIBI_COEFF head=(\d+) exponent=(\d+) live=([0-9a-f]{8}) ggml=([0-9a-f]{8}) live_fcsr=(\d+) ggml_fcsr=(\d+)\r?$', log, re.M)
        require(len(coeff) == 32 and [int(r[0]) for r in coeff] == list(range(32)), 'Incomplete coefficient inventory')
        bits = [int(r[0]) for r in coeff if r[2] != r[3]]
        flags = [int(r[0]) for r in coeff if r[4] != r[5]]
        marker = re.search(r'ALIBI_TARGET_DONE comparisons=32 bit_differences=(\d+) fcsr_differences=(\d+) full_mismatches=0 status=0', log)
        require(marker and int(marker[1]) == len(bits) and int(marker[2]) == len(flags), 'Incomplete probe/summary')
        require('ALIBI_TYPES float_uint32=double powf=float float_float=float' in log and 'Kernel panic' not in log,
                'Type assertions/probe exit failed')
        for path, digest in pins.items():
            require(sha(path) == digest, 'Post-probe input drift: ' + path)
        result.update(state='ALIBI_GNU14_GLIBC_PROBE_CHECKED', coefficient_bits_equal=not bits,
            coefficient_fcsr_equal=not flags, bit_difference_heads=bits, fcsr_difference_heads=flags,
            coefficients=[dict(head=int(h), exponent=int(e), live=a, ggml=b, live_fcsr=int(fa), ggml_fcsr=int(fb))
                          for h, e, a, b, fa, fb in coeff],
            post_pins_match=True, observed_elf_sha256=sha(elf), source_pins_sha256=sha(OUT / 'source-pins.json'),
            scope='H32/max_bias8 target glibc coefficient probe only; no model or RTL acceptance')
    except BaseException as exc:
        result['error'] = repr(exc)
    if not (OUT / 'source-pins.json').exists():
        save(OUT / 'source-pins.json', pins)
    save(OUT / 'commands.json', commands)
    save(OUT / 'result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return result['state'] != 'ALIBI_GNU14_GLIBC_PROBE_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
