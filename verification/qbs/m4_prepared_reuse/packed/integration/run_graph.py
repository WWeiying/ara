#!/usr/bin/env python3
"""Check combined packed preparation/cache dispatch through actual GGML graphs."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
from stage import HERE, ROOT, RUNTIME, atomic_json, digest, hashes, once
sys.path.insert(0, str(HERE.parents[1]))
from run_runtime_graph import check as check_graph


def check(text):
    result = check_graph(text)
    mode, counts = None, Counter()
    for line in text.splitlines():
        if line.startswith('M4_RUNTIME_GRAPH_MODE mode='):
            mode = int(line.rsplit('=', 1)[1])
        elif line.startswith('GGML_RISCV_QBS_M4_SELECTED '):
            fields = dict(word.split('=', 1) for word in line.split()[1:])
            if mode not in (0, 1) or fields.get('tag') != str(mode + 1) or fields.get('k') != '1536':
                raise ValueError('Wrong producer identity or selection scope')
            source = fields['source']
            event = fields.get('path') if source == 'direct' else fields.get('event')
            expected_fields = {'source', 'tag', 'k', 'path' if source == 'direct' else 'event'}
            if set(fields) != expected_fields or source not in ('direct', 'cache'):
                raise ValueError('Unknown selection schema')
            counts[(mode, source, event)] += 1
    expected = Counter({(0, 'direct', 'rvv'): 60, (0, 'direct', 'generic'): 12,
                        (1, 'direct', 'rvv'): 36, (1, 'direct', 'generic'): 12,
                        (1, 'cache', 'compute_rvv'): 12, (1, 'cache', 'hit'): 12})
    if counts != expected:
        raise ValueError('Combined selection accounting: ' + repr(counts))
    result.update(producer_selection=[dict(mode=m, source=s, event=e, count=n)
                                     for (m,s,e),n in sorted(counts.items())],
                  scope='Private combined GGML graph byte/state/dispatch acceptance, not installed runtime or performance')
    return result


def linked_providers(text, expected):
    provider, found = None, {}
    for line in text.split('Linker script and memory map', 1)[1].splitlines():
        match = re.match(r'^\s*(?:\.\S+\s+)?0x[0-9a-f]+\s+0x[0-9a-f]+\s+(.+\.o\)?)$', line)
        if match:
            provider = match[1]
        if 'ggml_backend_cpu_repack_buffer_type()' in line or (
                'ggml_riscv_qbs_q4_k_tag,' in line and '::forward_mul_mat(ggml_compute_params*, ggml_tensor*)' in line):
            symbol = line.split(None, 1)[1]
            if symbol in found or provider != str(expected):
                raise ValueError('Wrong/duplicate integration symbol provider')
            found[symbol] = provider
    if len(found) != 2:
        raise ValueError('Integration symbols not linked')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out, candidate = args.output.resolve(), args.candidate.resolve(strict=True)
    if not out.is_relative_to(ROOT / 'verification/out') or out.exists():
        raise ValueError('Fresh independent output required')
    pins = json.loads((candidate / 'manifest.json').read_text())
    if json.loads((candidate / 'result.json').read_text())['state'] != 'COMPILE_ONLY_PASS' or hashes(map(Path, pins)) != pins:
        raise ValueError('Private staged build drift')
    reference = ROOT / 'verification/out/m4-vector-runtime-graph-20261027-01'
    oldpins = json.loads((reference / 'manifest.json').read_text())
    source = reference / 'test.cpp'
    text = source.read_text()
    text = once(text, '    env("GGML_RISCV_QBS_M4_CACHE",mode ? "1":"0");',
                '    env("GGML_RISCV_QBS_M4_CACHE",mode ? "1":"0");\n'
                '    env("GGML_RISCV_QBS_M4_PACKED",mode ? "1":"0");')
    recipe = reference / 'initramfs.list'
    entries = [shlex.split(line) for line in recipe.read_text().splitlines() if line.strip()]
    command = json.loads((reference / 'qemu.command.json').read_text())
    inputs = [source, reference / 'data.S', recipe, Path(command[0]),
              Path(command[command.index('-kernel')+1]), Path(command[command.index('-bios')+1])]
    inputs.extend(Path(row[2]) for row in entries if row[:2] == ['file', '/init'])
    for path in inputs:
        if oldpins.get(str(path)) != digest(path):
            raise ValueError('Reference driver/image drift: ' + str(path))
    pins.update(hashes([*inputs, Path(__file__), HERE / 'stage.py',
                       HERE.parents[1] / 'run_runtime_graph.py', candidate / 'result.json']))
    libraries = json.loads((RUNTIME / 'result.json').read_text())['libraries']
    if len(libraries) != 4 or any(path not in pins for path in libraries):
        raise ValueError('Normal pinned library set')
    out.mkdir(parents=True)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None, installed=False,
                 object_overrides=True, performance_measured=False, rtl_changed=False)

    def run(argv, label, limit):
        argv = list(map(str, argv))
        atomic_json(out / (label + '.command.json'), argv)
        with (out / (label + '.log')).open('x') as log:
            with subprocess.Popen(argv, cwd=out, stdout=log, stderr=log) as process:
                state.update(state=label.upper(), child_pid=process.pid)
                atomic_json(out / 'status.json', state)
                try:
                    code = process.wait(timeout=limit)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise
        atomic_json(out / (label + '.exit.json'), dict(returncode=code))
        if code:
            raise RuntimeError(label + ' failed')

    try:
        test = out / 'test.cpp'
        test.write_text(text)
        objects = []
        for name, path in (('test', test), ('data', reference / 'data.S')):
            argv = json.loads((reference / ('compile-' + name + '.command.json')).read_text())
            compiler = argv[0]
            obj = out / (name + '.o')
            argv[argv.index('-c')+1] = str(path)
            argv[argv.index('-o')+1] = str(obj)
            run(argv, 'compile-' + name, 180)
            objects.append(obj)
        run([compiler, '-static', *objects, candidate / 'repack.o', *libraries,
             '-ldl', '-lm', '-pthread', '-Wl,-Map=' + str(out / 'link.map'), '-o', out / 'test'], 'link', 180)
        atomic_json(out / 'link-audit.json', linked_providers((out / 'link.map').read_text(), candidate / 'repack.o'))
        selected = [row for row in entries if row[:2] == ['file', '/test']]
        if len(selected) != 1:
            raise ValueError('Initramfs test selection')
        selected[0][2] = str(out / 'test')
        listing = out / 'initramfs.list'
        listing.write_text(''.join(' '.join(row) + '\n' for row in entries))
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out / 'initramfs.cpio').open('xb') as stream:
            subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([test, *objects, out / 'test', listing, out / 'initramfs.cpio',
                           cpio, out / 'link.map', out / 'link-audit.json']))
        atomic_json(out / 'manifest.json', pins)
        command[command.index('-initrd')+1] = str(out / 'initramfs.cpio')
        run(command, 'qemu', 600)
        measured = check((out / 'qemu.log').read_text())
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Runtime input drift')
        state.update(state='PASS', measured=measured, log_sha256=digest(out / 'qemu.log'))
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        raise
    finally:
        state['child_pid'] = None
        atomic_json(out / 'status.json', state)
        atomic_json(out / 'result.json', state)


if __name__ == '__main__':
    main()
