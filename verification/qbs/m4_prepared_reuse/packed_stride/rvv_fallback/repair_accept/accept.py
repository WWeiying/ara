#!/usr/bin/env python3
"""Bounded private acceptance; never installs the candidate."""
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
OUT = ROOT / 'verification/out/m4-stride-rvv-repair-20261027-02'
BASE = ROOT / 'verification/out/m4-stride-rvv-fallback-20261027-01'
RUNTIME = ROOT / 'verification/out/m4-prepared-installed-build-20261027-01'
ACTIVE = ROOT / 'verification/out/m4-packed-qkv-vcs-20261027-01/source-pins.json'
ACTIVE_SHA = '06097034f29a8f21b0b83e877ba9aebecb4e9ea7b4356cefb119bab4449f475d'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def merge(pins, added):
    require(all(p not in pins or pins[p] == v for p, v in added.items()), 'Conflicting inherited pins')
    pins.update(added)


def verify(pins):
    require(all(Path(p).is_file() and digest(p) == v for p, v in pins.items()), 'Pinned input drift')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'Wrong worktree')
    OUT.mkdir(parents=True, exist_ok=False)
    pins = {}
    state = dict(state='PREFLIGHT', pid=os.getpid(), qemu_runs=0, qemu_limit_seconds=180,
                 installed=False, object_overrides=True, rtl_changed=False, performance_measured=False)

    def save(name, value):
        (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

    def pin(paths):
        merge(pins, {str(p): digest(p) for p in paths})

    def run(argv, label, limit=180, cwd=OUT, binary=None):
        argv = list(map(str, argv))
        save(label + '.command.json', dict(argv=argv, cwd=str(cwd), limit_seconds=limit))
        start = time.monotonic()
        code, timed_out = None, False
        with (OUT / (label + '.log')).open('xb') as log:
            target = binary.open('xb') if binary else log
            try:
                with subprocess.Popen(argv, cwd=cwd, stdout=target, stderr=log) as process:
                    state.update(state=label.upper(), child_pid=process.pid)
                    save('status.json', state)
                    print(label, process.pid, flush=True)
                    try:
                        code = process.wait(timeout=limit)
                    except BaseException as exc:
                        timed_out = isinstance(exc, subprocess.TimeoutExpired)
                        process.kill()
                        code = process.wait()
                        raise
            finally:
                if binary:
                    target.close()
                save(label + '.exit.json', dict(returncode=code, timed_out=timed_out,
                     host_elapsed_seconds=time.monotonic()-start, timing_scope='workflow only'))
        require(code == 0, label + ' failed')

    try:
        require(digest(ACTIVE) == ACTIVE_SHA and len(read(ACTIVE)) == 1880, 'Active inventory identity')
        for inventory in (ACTIVE, RUNTIME / 'manifest.json', BASE / 'source-pins.json', BASE / 'manifest.json'):
            merge(pins, read(inventory))
            pin([inventory])
        require(read(BASE / 'result.json')['measured']['cases'][0]['mismatches'] == 96, 'Frozen failure')
        pin([p for p in BASE.iterdir() if p.is_file()])
        pin([p for p in HERE.iterdir() if p.is_file()])
        pin([HERE.parent / 'general_transform.py', HERE.parent.parent / 'repair.py',
             HERE.parent.parent / 'strided_input.h'])
        committed = subprocess.check_output(['git', 'show', '30c89b228:verification/qbs/m4_prepared_reuse/packed_stride/rvv_fallback/general_transform.py'], cwd=ROOT)
        require(committed == (HERE.parent / 'general_transform.py').read_bytes(), 'Candidate differs from reviewed commit')
        source = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp')
        database = RUNTIME / 'build/compile_commands.json'
        record, = [r for r in read(database) if Path(r['file']).resolve() == source]
        command = shlex.split(record['command'])
        pin([database, source, Path(command[0]), Path(command[0]).resolve()])
        verify(pins)
        save('source-pins.json', pins)
        save('preflight.json', dict(active_entries=1880, active_sha256=ACTIVE_SHA,
             merged_entries=len(pins), conflicts=0, inherited_check='PASS', original_test_object=str(BASE/'test.o')))
        # Generate an explicit successor with exactly one accounting-line change.
        old = (HERE.parent / 'check.py').read_text()
        before = '[dict(enabled="0", path="generic", k="512")]*3'
        after = '[dict(enabled="0", path="generic", k="512")]*2 + [dict(enabled="0", path="generic", k="256")]*2'
        require(old.count(before) == 1 and (HERE/'check.py').read_text() == old.replace(before, after), 'Checker changed beyond producer accounting')
        transform = load('general_stride_candidate', HERE.parent / 'general_transform.py').transform
        original = source.read_text()
        repaired = transform(original)
        (OUT/'repack.cpp').write_text(repaired)
        (OUT/'repair.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True), repaired.splitlines(True), fromfile=str(source), tofile=str(OUT/'repack.cpp'))))
        command[command.index('-c')+1] = str(OUT/'repack.cpp')
        command[command.index('-o')+1] = str(OUT/'repack.o')
        for flag in ('-MF', '-MT'):
            if flag in command:
                command[command.index(flag)+1] = str(OUT/('repack.d' if flag == '-MF' else 'repack.o'))
        command += ['-iquote', str(source.parent), '-I'+str(HERE.parent.parent)]
        run(command, 'compile-repair', cwd=record['directory'])
        link = read(BASE/'link.command.json')['argv']
        libs = read(BASE/'result.json')['normal_libraries']
        require(len(libs) == 4 and all(p in pins and p in link for p in libs), 'Normal archives')
        require(link[2] == str(BASE/'test.o'), 'Original test object')
        link.insert(3, str(OUT/'repack.o'))
        link[link.index('-o')+1] = str(OUT/'test')
        link = ['-Wl,-Map='+str(OUT/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        run(link, 'link')
        nm = Path(command[0]).with_name('riscv64-linux-nm')
        pin([nm, nm.resolve()])
        run([nm, '-C', '--defined-only', OUT/'repack.o'], 'private-symbols')
        run([nm, '-C', '--defined-only', OUT/'test'], 'linked-symbols')
        symbol = 'ggml::cpu::repack::tensor_traits'
        ordinary = [l.split(' ', 2)[-1] for l in (OUT/'private-symbols.log').read_text().splitlines()
                    if 'block_q4_Kx32,' in l and 'forward_mul_mat(' in l]
        require(len(ordinary) == 1, 'Ordinary block_q4_Kx32 trait missing/ambiguous')
        require(ordinary[0] in (OUT/'linked-symbols.log').read_text(), 'Linked ordinary trait absent')
        mapping = (OUT/'link.map').read_text().splitlines()
        provider = [i for i, l in enumerate(mapping) if ordinary[0] in l]
        require(provider and all(str(OUT/'repack.o') in '\n'.join(mapping[max(0,i-4):i]) for i in provider), 'Private symbol provider not proven')
        save('symbol-provider.json', dict(symbol=ordinary[0], provider=str(OUT/'repack.o'), ordinary_not_qbs=True,
             map_lines=[mapping[max(0,i-4):i+1] for i in provider]))
        listing = (BASE/'initramfs.list').read_text()
        require(listing.count(str(BASE/'test')) == 1, 'Initramfs ELF entry')
        (OUT/'initramfs.list').write_text(listing.replace(str(BASE/'test'), str(OUT/'test')))
        cpio = read(BASE/'initramfs.command.json')['argv'][0]
        run([cpio, OUT/'initramfs.list'], 'initramfs', 30, binary=OUT/'initramfs.cpio')
        pin([OUT/name for name in ('repack.cpp','repair.patch','repack.o','test','link.map','initramfs.list','initramfs.cpio')])
        save('manifest.json', pins)
        verify(pins)
        qemu = read(BASE/'qemu.command.json')['argv']
        require(qemu[qemu.index('-cpu')+1] == 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=false', 'CPU drift')
        qemu[qemu.index('-initrd')+1] = str(OUT/'initramfs.cpio')
        state['qemu_runs'] = 1
        run(qemu, 'qemu', 180)
        measured = load('repair_successor_check', HERE/'check.py').check((OUT/'qemu.log').read_text())
        save('comparison.json', measured)
        require(measured['completed_cases'] == 4 and measured['native_qbs_calls'] == 0 and
                all(c['mismatches'] == 0 for c in measured['cases']), 'Repair acceptance failed')
        run([sys.executable, '-B', HERE/'test_check.py', '--log', OUT/'qemu.log'], 'checker-tests', 30)
        verify(pins)
        require(digest(ACTIVE) == ACTIVE_SHA, 'Active inventory changed')
        state.update(state='PASS', measured=measured, active_inventory_unchanged=True,
                     input_sha_check_after='PASS', log_sha256=digest(OUT/'qemu.log'),
                     scope='Private ordinary RVV functional acceptance only; no installed runtime, RTL or performance claim')
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        save('status.json', state)
        save('result.json', state)
        print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()
