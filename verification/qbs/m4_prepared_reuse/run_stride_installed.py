#!/usr/bin/env python3
"""Replay accepted ordinary-RVV stride cases with four normal runtime libraries."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out, runtime = args.output.resolve(), args.runtime_build.resolve(strict=True)
    if not out.is_relative_to(ROOT / 'verification/out') or out.exists():
        raise ValueError('Fresh independent output required')
    reference = ROOT / 'verification/out/m4-stride-rvv-repair-20261027-04'
    old = json.loads((reference / 'manifest.json').read_text())
    pins = json.loads((runtime / 'manifest.json').read_text())
    build = json.loads((runtime / 'result.json').read_text())
    if build['state'] != 'PASS' or hashes(map(Path, pins)) != pins:
        raise ValueError('Normal build identity')
    if json.loads((reference / 'result.json').read_text())['state'] != 'PASS':
        raise ValueError('Missing accepted reference')
    libraries = build['libraries']
    if len(libraries) != 4 or {Path(p).name for p in libraries} != {'libllama.a', 'libggml.a', 'libggml-cpu.a', 'libggml-base.a'}:
        raise ValueError('Expected normal libraries only')
    command = json.loads((reference / 'compile-test.command.json').read_text())['argv']
    qemu = json.loads((reference / 'qemu.command.json').read_text())['argv']
    entries = [shlex.split(line) for line in (reference / 'initramfs.list').read_text().splitlines()]
    inputs = [reference / 'test.cpp', Path(qemu[0]), Path(qemu[qemu.index('-bios') + 1]),
              Path(qemu[qemu.index('-kernel') + 1])]
    inputs += [Path(row[2]) for row in entries if row[0] == 'file' and row[1] != '/test']
    for path in inputs:
        if old.get(str(path)) != digest(path):
            raise ValueError('Accepted driver/data/tool drift: ' + str(path))
    if qemu[qemu.index('-cpu') + 1] != 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=false':
        raise ValueError('Ordinary RVV CPU expected')
    checker = HERE / 'packed_stride/rvv_fallback/repair_accept/check.py'
    pins.update(hashes([*inputs, checker, Path(__file__), runtime / 'result.json']))
    spec = importlib.util.spec_from_file_location('stride_checker', checker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out.mkdir(parents=True)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, object_overrides=False)

    def run(argv, label, limit):
        argv = list(map(str, argv))
        atomic_json(out / (label + '.command.json'), argv)
        state.update(state=label.upper(), child_pid=None)
        atomic_json(out / 'status.json', state)
        def started(pid):
            state['child_pid'] = pid
            atomic_json(out / 'status.json', state)
        if run_command(argv, out / (label + '.log'), limit, os.environ.copy(), started):
            raise RuntimeError(label + ' failed')

    try:
        command[command.index('-o') + 1] = str(out / 'test.o')
        run(command, 'compile', 180)
        run([command[0], '-static', out / 'test.o', *libraries, '-ldl', '-lm', '-pthread',
             '-Wl,-Map=' + str(out / 'link.map'), '-o', out / 'test'], 'link', 180)
        mapping = (out / 'link.map').read_text()
        if 'libggml-cpu.a(repack.cpp.o)' not in mapping or str(reference.parent / 'm4-stride-rvv-repair-20261027-02/repack.o') in mapping:
            raise ValueError('Normal repack provider missing or private override present')
        for row in entries:
            if row[:2] == ['file', '/test']:
                row[2] = str(out / 'test')
        listing = out / 'initramfs.list'
        listing.write_text(''.join(' '.join(row) + '\n' for row in entries))
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([cpio, listing, out / 'test.o', out / 'test', out / 'link.map', out / 'initramfs.cpio']))
        atomic_json(out / 'manifest.json', pins)
        qemu[qemu.index('-initrd') + 1] = str(out / 'initramfs.cpio')
        run(qemu, 'qemu', 180)
        measured = module.check((out / 'qemu.log').read_text())
        if measured['completed_cases'] != 4 or measured['native_qbs_calls'] != 0:
            raise ValueError('Ordinary RVV scope')
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Execution source drift')
        state.update(state='PASS', measured=measured, performance_measured=False,
                     log_sha256=digest(out / 'qemu.log'), normal_libraries=libraries)
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        atomic_json(out / 'status.json', state)
        atomic_json(out / 'result.json', state)


if __name__ == '__main__':
    main()
