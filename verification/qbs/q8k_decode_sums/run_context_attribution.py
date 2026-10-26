#!/usr/bin/env python3
"""Relink a sealed real-model test with an independently compiled QBS probe."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
sys.path.insert(0, str(ROOT / 'verification/qbs/combined_zvfh_m4/model'))
from native_audit import audit
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    probe = args.probe.resolve(strict=True)
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Use independent verification/out')
    base = ROOT / 'verification/out/q8k-signed-max-model-20261026-01'
    if json.loads((base / 'result.json').read_text())['state'] != 'PASS':
        raise ValueError('Original model gate did not pass')
    if json.loads((probe / 'result.json').read_text())['state'] != 'COMPILE_ONLY_PASS':
        raise ValueError('Probe did not compile')
    archived = json.loads((base / 'manifest.json').read_text())
    link = json.loads((base / 'link.command.json').read_text())
    artifacts = [Path(x) for x in link if x.endswith(('.a', '.o'))]
    qemu = json.loads((base / 'qemu.command.json').read_text())
    artifacts += [base / 'init', Path(qemu[0]), Path(qemu[qemu.index('-bios')+1]),
                  Path(qemu[qemu.index('-kernel')+1])]
    drive = qemu[qemu.index('-drive')+1]
    if not drive.endswith(',readonly=on'):
        raise ValueError('Model drive must remain read-only')
    artifacts.append(Path(drive.split(',')[0].removeprefix('file=')))
    for path in artifacts:
        if archived.get(str(path)) != digest(path):
            raise ValueError('Sealed model artifact drift: ' + str(path))
    inputs = artifacts + [probe / name for name in
                         ('probe.o', 'qbs_context_attribution.cpp', 'result.json', 'command.json')]
    inputs += [Path(__file__), base / 'manifest.json', base / 'link.command.json', base / 'qemu.command.json']
    pins = hashes(inputs)
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out / 'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def run(argv, name, bound):
        state.update(state=name.upper(), child_pid=None)
        save()
        atomic_json(out / (name + '.command.json'), argv)
        if run_command(argv, out / (name + '.log'), bound, os.environ.copy(), started):
            raise RuntimeError(name + ' failed')
        state['child_pid'] = None
    try:
        # Explicit object precedes archives, so the original QBS archive member
        # is not selected. Other model/runtime objects remain the sealed ones.
        link.insert(2, str(probe / 'probe.o'))
        link[link.index('-o')+1] = str(out / 'test')
        link = [('-Wl,-Map=' + str(out / 'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
        run(link, 'link', 180)
        listing = out / 'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                           'dir /model 755 0 0\ndir /tmp 1777 0 0\n'
                           f'file /init {base / "init"} 755 0 0\nfile /test {out / "test"} 755 0 0\n')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([cpio, listing, out / 'test', out / 'initramfs.cpio', out / 'link.map']))
        atomic_json(out / 'manifest.json', pins)
        qemu[qemu.index('-initrd')+1] = str(out / 'initramfs.cpio')
        run(qemu, 'qemu', 7200)
        text = (out / 'qemu.log').read_text()
        result = audit(text)
        records = [line for line in text.splitlines() if line.startswith('GGML_RISCV_QBS_CONTEXT_LOOKAHEAD ')]
        if not records:
            raise ValueError('Attribution probe did not execute')
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Input drift')
        result.update(attribution_records=len(records), runtime_modified=False,
                      performance_measured=False, log_sha256=digest(out / 'qemu.log'))
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
