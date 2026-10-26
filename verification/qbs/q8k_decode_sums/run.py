#!/usr/bin/env python3
"""Bounded functional gate for the private Decode block-sum helper, not timing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, hashes, digest
from run_tile_context_engine import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use verification/out')
    out.mkdir(parents=True, exist_ok=False)
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    cc = platform/'tools/bin/riscv64-linux-gcc'
    qemu = ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    cpio = platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    init = ROOT/'verification/akv/quantized_kv/ggml_live/init.c'
    kernel, firmware = platform/'images/Image', platform/'images/fw_dynamic.bin'
    paths = [HERE/'test.c', HERE/'sums.h', Path(__file__), cc.resolve(), qemu, cpio, init, kernel, firmware]
    pins = hashes(paths)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out/'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def run(argv, name, bound):
        argv = list(map(str, argv))
        state['state'] = name.upper()
        save()
        atomic_json(out/(name+'.command.json'), argv)
        if run_command(argv, out/(name+'.log'), bound, os.environ.copy(), started):
            raise RuntimeError(name+' failed')
        state['child_pid'] = None
        save()
    save()
    atomic_json(out/'source-pins.json', pins)
    try:
        run([cc, '-std=gnu11', '-march=rv64gcv', '-mabi=lp64d', '-O3', '-fno-tree-vectorize',
             '-fno-fast-math', '-ffp-contract=off', '-frounding-math', '-Wall', '-Wextra', '-Werror',
             '-static', HERE/'test.c', '-lm', '-o', out/'test'], 'compile', 120)
        run([cc, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', init, '-o', out/'init'], 'init', 120)
        listing = out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                           f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
        pins.update(hashes([listing, out/'initramfs.cpio', out/'test', out/'init']))
        atomic_json(out/'source-pins.json', pins)
        marker = 'Q8K_DECODE_SUMS_PASS checks=33280'
        for vlen in (128, 256, 512, 1024):
            name = 'qemu-'+str(vlen)
            run([qemu, '-M', 'virt', '-cpu', f'rv64,v=true,vlen={vlen},elen=64', '-smp', '1', '-m', '512M',
                 '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-bios', firmware,
                 '-kernel', kernel, '-initrd', out/'initramfs.cpio',
                 '-append', 'console=ttyS0 rdinit=/init'], name, 600)
            lines = (out/(name+'.log')).read_text().splitlines()
            if lines.count(marker) != 1 or lines.count('GUEST_TEST_EXIT=0') != 1:
                raise ValueError('Missing complete helper/guest success')
            if any('Q8K_DECODE_SUMS_FAIL' in line or 'Kernel panic' in line for line in lines):
                raise ValueError('Guest error')
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Source/artifact drift')
        result = dict(state='PASS', vlen=[128,256,512,1024], patterns_per_vlen=260, checks_per_vlen=33280,
                      production_integrated=False, full_quantizer_tested=False, performance_measured=False,
                      source_pins_sha256=digest(out/'source-pins.json'),
                      logs={str(v):digest(out/f'qemu-{v}.log') for v in (128,256,512,1024)})
        atomic_json(out/'result.json', result)
        state['state'] = 'PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out/'result.json', state)
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
