#!/usr/bin/env python3
"""Actual original-vs-candidate Decode quantizer model A/B, with fixed M4 policy."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
sys.path.insert(0, str(ROOT / 'verification/qbs/combined_zvfh_m4/model'))
from native_audit import native_accounting
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command


def check(text):
    lines = text.splitlines()
    if lines.count('Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured') != 1 or lines.count('GUEST_TEST_EXIT=0') != 1:
        raise ValueError('Missing complete paired-model success')
    if 'Q8K_MODEL_FAIL' in text or 'Kernel panic' in text:
        raise ValueError('Guest failure')
    expected = [f'Q8K_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                for k in range(2) for s in range(3)]
    if [s for s in lines if s.startswith('Q8K_MODEL_COMPARE ')] != expected:
        raise ValueError('Incomplete/duplicate comparisons')
    dispatch = re.findall(r'^DECODE_LAYOUT_DISPATCH original=(\d+) candidate=(\d+)$', text, re.M)
    # Normalize CRLF before invoking this checker.
    if len(dispatch) != 2:
        raise ValueError('Missing per-process quantizer dispatch')
    a, b = [tuple(map(int, pair)) for pair in dispatch]
    if not (a[0] > 0 and a[1] == 0 and b[0] == 0 and b[1] == a[0]):
        raise ValueError('Quantizer toggle absent or workload changed')
    return dict(state='PASS', comparisons=6, logits_compared=6*151936,
                original_calls=a[0], candidate_calls=b[1],
                native_execution=native_accounting(text), performance_measured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Use independent verification/out')
    base = ROOT / 'verification/out/q8k-signed-max-model-20261026-01'
    gate = ROOT / 'verification/out/q8k-decode-layout-full-20261026-01'
    pins = json.loads((gate / 'source-pins.json').read_text())
    if json.loads((gate / 'result.json').read_text())['state'] != 'PASS' or hashes(map(Path, pins)) != pins:
        raise ValueError('Quantizer gate drift')
    archived = json.loads((base / 'manifest.json').read_text())
    link = json.loads((base / 'link.command.json').read_text())
    command = json.loads((base / 'compile.command.json').read_text())
    qemu = json.loads((base / 'qemu.command.json').read_text())
    artifacts = [Path(x) for x in link if x.endswith(('.a', '.o'))]
    artifacts += [base / 'init', base / 'test.cpp', Path(qemu[0]),
                  Path(qemu[qemu.index('-bios')+1]), Path(qemu[qemu.index('-kernel')+1]),
                  Path(qemu[qemu.index('-drive')+1].split(',')[0].removeprefix('file='))]
    for path in artifacts:
        if archived.get(str(path)) != digest(path):
            raise ValueError('Sealed model artifact drift: '+str(path))
    pins.update(hashes(artifacts + [Path(__file__), HERE / 'model_layout_wrapper.c']))
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out / 'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def run(argv, name, bound):
        state.update(state=name.upper(), child_pid=None)
        save()
        atomic_json(out / (name+'.command.json'), argv)
        if run_command(argv, out / (name+'.log'), bound, os.environ.copy(), started):
            raise RuntimeError(name+' failed')
        state['child_pid'] = None
    try:
        text = (base / 'test.cpp').read_text()
        old = 'env("GGML_RISCV_QBS_M4_PREPARE", mode ? "1" : "0");'
        if text.count(old) != 1:
            raise ValueError('Model harness drift')
        text = text.replace(old, 'env("GGML_RISCV_QBS_M4_PREPARE", "1");\n'
                            '    env("GGML_QBS_DECODE_LAYOUT_TEST", mode ? "1" : "0");')
        (out / 'test.cpp').write_text(text)
        command[command.index('-c')+1] = str(out / 'test.cpp')
        command[command.index('-o')+1] = str(out / 'test.o')
        run(command, 'compile', 180)
        cc = '/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc'
        run([cc, '-std=gnu11', '-O3', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
             '-fno-fast-math', '-ffp-contract=off', '-I'+str(gate), '-I'+str(HERE),
             '-c', str(HERE / 'model_layout_wrapper.c'), '-o', str(out / 'wrapper.o')], 'wrapper', 180)
        link[2] = str(out / 'test.o')
        link.insert(3, str(out / 'wrapper.o'))
        link.append('-Wl,--wrap=quantize_row_q8_K')
        link[link.index('-o')+1] = str(out / 'test')
        link = ['-Wl,-Map='+str(out / 'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        run(link, 'link', 180)
        listing = out / 'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                           'dir /model 755 0 0\ndir /tmp 1777 0 0\n'
                           f'file /init {base / "init"} 755 0 0\nfile /test {out / "test"} 755 0 0\n')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([Path(cc).resolve(), cpio] + [out / n for n in
                    ('test.cpp','test.o','wrapper.o','test','link.map','initramfs.list','initramfs.cpio')]))
        atomic_json(out / 'manifest.json', pins)
        qemu[qemu.index('-initrd')+1] = str(out / 'initramfs.cpio')
        run(qemu, 'qemu', 7200)
        result = check((out / 'qemu.log').read_text())
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Execution drift')
        result.update(log_sha256=digest(out / 'qemu.log'), runtime_modified=False,
                      scope='Original vs layout Decode quantizer; M4 preparation fixed ON')
        atomic_json(out / 'result.json', result)
        state['state'] = 'PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out / 'result.json', state)
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__':
    main()
