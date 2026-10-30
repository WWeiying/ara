#!/usr/bin/env python3
"""Bounded functional gate for the complete Decode quantizer candidate, not timing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import struct
import math
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
    llama = Path('/home/wangwy/llama/llama.cpp')
    source = llama/'ggml/src/ggml-cpu/arch/riscv/quants.c'
    common = llama/'ggml/src/ggml-common.h'
    text = source.read_text()
    start = text.index('void quantize_row_q8_K(')
    end = text.index('//===================================== Dot products', start)
    original = text[start:end]
    first = original.index('            // first iteration clear')
    last = original.index('            rem -= vl;', first)
    candidate = original[:first] + '            qbs_decode_sums_split_candidate(v_q, vl, y_block->bsums + offset/16);\n' + original[last:]
    candidate = candidate.replace('        vint16m1_t v_zero_sum = __riscv_vmv_v_x_i16m1(0, 1);\n', '')
    prefix = '#define GGML_COMMON_DECL_C\n#include "' + str(common) + '"\n#include "sums_split.h"\n#include <assert.h>\n#include <math.h>\n#include <string.h>\n#define GGML_RESTRICT restrict\n'
    generated = out/'quantizers.h'
    generated.write_text(prefix +
        original.replace('void quantize_row_q8_K(', 'static __attribute__((noinline)) void decode_original(', 1) +
        candidate.replace('void quantize_row_q8_K(', 'static __attribute__((noinline)) void decode_candidate(', 1))
    paths = [source, common, generated, HERE/'real_test.c', HERE/'sums_split.h', Path(__file__), cc.resolve(), qemu, cpio, init, kernel, firmware]
    capture_root = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/decode/operators')
    names = ('attn_q','attn_k','attn_v','attn_output','ffn_gate','ffn_up','ffn_down')
    lengths, declarations = [], []
    for index, name in enumerate(names):
        folder = capture_root/('blk_0_'+name+'_weight')
        raw, meta_path = folder/'activation_f32.bin', folder/'activation_f32.json'
        meta = json.loads(meta_path.read_text())
        data = raw.read_bytes()
        k = meta['shape'][0]
        if meta['type'] != 'f32' or meta['shape'] != [k,1,1,1] or k not in (1536,8960) or len(data) != k*4 or meta['nbytes'] != len(data) or meta['strides'] != [4,k*4,k*4,k*4]:
            raise ValueError('Unexpected capture geometry')
        if not all(math.isfinite(v) for v in struct.unpack('<'+str(k)+'f', data)):
            raise ValueError('Nonfinite captured input')
        values = struct.unpack('<'+str(k)+'I', data)
        declarations.append('static const uint32_t capture_'+str(index)+'[] = {'+','.join(hex(v)+'u' for v in values)+'};')
        lengths.append(k)
        paths += [raw, meta_path]
    captures = out/'captures.h'
    captures.write_text('\n'.join(declarations)+'\nstatic const uint32_t *capture_data[] = {'+','.join('capture_'+str(i) for i in range(7))+'};\nstatic const unsigned capture_lengths[] = {'+','.join(map(str,lengths))+'};\n')
    paths.append(captures)
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
             '-I'+str(out), '-I'+str(HERE), '-static', HERE/'real_test.c', '-lm', '-o', out/'test'], 'compile', 120)
        run([cc, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', init, '-o', out/'init'], 'init', 120)
        listing = out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                           f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
        pins.update(hashes([listing, out/'initramfs.cpio', out/'test', out/'init']))
        atomic_json(out/'source-pins.json', pins)
        marker = 'Q8K_DECODE_REAL_PASS checks=280'
        for vlen in (128, 256, 512, 1024):
            name = 'qemu-'+str(vlen)
            run([qemu, '-M', 'virt', '-cpu', f'rv64,v=true,vlen={vlen},elen=64', '-smp', '1', '-m', '512M',
                 '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-bios', firmware,
                 '-kernel', kernel, '-initrd', out/'initramfs.cpio',
                 '-append', 'console=ttyS0 rdinit=/init'], name, 600)
            lines = (out/(name+'.log')).read_text().splitlines()
            if lines.count(marker) != 1 or lines.count('GUEST_TEST_EXIT=0') != 1:
                raise ValueError('Missing complete helper/guest success')
            if any('Q8K_DECODE_REAL_FAIL' in line or 'Kernel panic' in line for line in lines):
                raise ValueError('Guest error')
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Source/artifact drift')
        result = dict(state='PASS', vlen=[128,256,512,1024], real_captures_per_vlen=7, checks_per_vlen=280,
                      production_integrated=False, full_quantizer_tested=True, performance_measured=False,
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
