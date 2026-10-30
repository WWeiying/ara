#!/usr/bin/env python3
"""Run the accepted 65-case matrix on normal libraries with packed enabled."""
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
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Fresh output required')
    reference = ROOT / 'verification/out/m4-stride-expanded-20261027-01'
    folder = HERE / 'packed_stride/expanded'
    old = json.loads((reference / 'acceptance-manifest.json').read_text())
    pins = json.loads((runtime / 'manifest.json').read_text())
    report = json.loads((runtime / 'result.json').read_text())
    if report['state'] != 'PASS' or hashes(map(Path, pins)) != pins:
        raise ValueError('Normal build identity')
    if json.loads((reference / 'acceptance-result.json').read_text())['state'] != 'PASS':
        raise ValueError('Missing accepted matrix')
    source, checker = folder / 'test.cpp', folder / 'check.py'
    for path in (source, checker):
        if old.get(str(path)) != digest(path):
            raise ValueError('Accepted test/checker drift')
    spec = importlib.util.spec_from_file_location('expanded_checker', checker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = module.matrix()
    libs = report['libraries']
    if len(libs) != 4 or {Path(p).name for p in libs} != {'libllama.a', 'libggml.a', 'libggml-cpu.a', 'libggml-base.a'}:
        raise ValueError('Normal library contract')
    command = json.loads((reference / 'compile-test.command.json').read_text())['argv']
    pins.update(hashes([source, checker, Path(__file__), runtime / 'result.json']))
    out.mkdir(parents=True)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, completed_cases=0,
                 object_overrides=False, performance_measured=False)

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
        text = source.read_text()
        marker = '    env("GGML_RISCV_QBS_M4_PREPARE", "1");'
        if text.count(marker) != 1 or 'GGML_RISCV_QBS_M4_PACKED' in text:
            raise ValueError('Driver selector drift')
        (out / 'test.cpp').write_text(text.replace(marker, marker + '\n    env("GGML_RISCV_QBS_M4_PACKED", "1");'))
        command[command.index('-c') + 1] = str(out / 'test.cpp')
        command[command.index('-o') + 1] = str(out / 'test.o')
        run(command, 'compile', 180)
        run([command[0], '-static', out / 'test.o', *libs, '-ldl', '-lm', '-pthread',
             '-Wl,-Map=' + str(out / 'link.map'), '-o', out / 'test'], 'link', 180)
        if 'libggml-cpu.a(repack.cpp.o)' not in (out / 'link.map').read_text():
            raise ValueError('Normal repack provider missing')
        pins.update(hashes([out / name for name in ('test.cpp', 'test.o', 'test', 'link.map')]))
        measured = []
        for typ in ('Q4_K', 'Q6_K', 'Q4_0', 'Q8_0'):
            directory = out / typ
            directory.mkdir()
            prior = reference / typ
            entries = [shlex.split(l) for l in (prior / 'initramfs.list').read_text().splitlines()]
            argv = json.loads((prior / 'qemu.command.json').read_text())['argv']
            used = [Path(argv[0]), Path(argv[argv.index('-bios') + 1]), Path(argv[argv.index('-kernel') + 1])]
            used += [Path(row[2]) for row in entries if row[0] == 'file' and row[1] != '/test']
            for path in used:
                if old.get(str(path)) != digest(path):
                    raise ValueError('Accepted asset drift: ' + str(path))
            for row in entries:
                if row[:2] == ['file', '/test']:
                    row[2] = str(out / 'test')
            listing = directory / 'initramfs.list'
            listing.write_text(''.join(' '.join(row) + '\n' for row in entries))
            cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
            with (directory / 'initramfs.cpio').open('xb') as stream:
                subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
            pins.update(hashes([*used, cpio, listing, directory / 'initramfs.cpio']))
            atomic_json(out / 'manifest.json', pins)
            argv[argv.index('-initrd') + 1] = str(directory / 'initramfs.cpio')
            run(argv, typ + '/qemu', 300)
            raw = (directory / 'qemu.log').read_text()
            selected = [c for c in cases if c['type'] == typ]
            result = module.check(raw, selected)
            if typ.endswith('_K'):
                records = [dict(w.split('=', 1) for w in l.split()[1:]) for l in raw.splitlines()
                           if l.startswith('GGML_RISCV_QBS_M4_SELECTED ')]
                if not records or any(r['tag'] != '2' or r['source'] != 'direct' for r in records) or not any(r['path'] == 'rvv' for r in records):
                    raise ValueError('Packed producer not exercised')
            measured.extend(result)
            state['completed_cases'] = len(measured)
            atomic_json(directory / 'comparison.json', result)
            pins.update(hashes([directory / 'qemu.log', directory / 'comparison.json']))
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Execution drift')
        atomic_json(out / 'manifest.json', pins)
        state.update(state='PASS', paired_cases=len(measured), paired_outputs=sum(c['outputs'] for c in measured),
                     native_commands=sum(c['native']['native_qbexec'] for c in measured))
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        atomic_json(out / 'status.json', state)
        atomic_json(out / 'result.json', state)


if __name__ == '__main__':
    main()
