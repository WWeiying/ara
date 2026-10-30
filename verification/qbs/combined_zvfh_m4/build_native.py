#!/usr/bin/env python3
"""Link real production selector and generic with an independent byte/CSR test."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from run_half_scale_soc import atomic_json, digest, hashes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'production-build', 'captures', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    candidate, production, captures = (x.resolve(strict=True) for x in
                                      (a.candidate, a.production_build, a.captures))
    report = json.loads((candidate / 'result.json').read_text())
    pins = json.loads((candidate / 'inputs.json').read_text())
    if (report['state'] != 'COMPILE_ONLY_PASS' or
        digest(candidate / 'inputs.json') != report['inputs_sha256'] or
        digest(candidate / 'candidate.o') != report['object_sha256'] or
        hashes(map(Path, pins)) != pins):
        raise ValueError('Candidate compile identity changed')
    old = json.loads((captures / 'manifest.json').read_text())
    names = ['captures.txt', 'captures.json', *('real_' + name + '.bin' for name in
             ('attn_first', 'attn_last', 'gate_first', 'gate_last', 'down_first', 'down_last'))]
    capture_files = [captures / name for name in names]
    if any(old.get(str(path)) != digest(path) for path in capture_files):
        raise ValueError('Real capture identity drift')
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    cc, cxx, objdump = [platform / ('tools/bin/riscv64-linux-' + name) for name in ('gcc', 'g++', 'objdump')]
    cpio = platform / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    ggml = Path('/home/wangwy/llama/llama.cpp/ggml')
    libs = [production / ('llama/ggml/src/lib' + name + '.a') for name in ('ggml', 'ggml-cpu', 'ggml-base')]
    sources = [*capture_files, *libs, candidate / 'candidate.o', candidate / 'result.json',
               candidate / 'inputs.json', captures / 'manifest.json', HERE / 'native.cpp', HERE / 'init.c',
               HERE / 'check_native.py', Path(__file__).resolve(), cc.resolve(), cxx.resolve(),
               objdump.resolve(), cpio]
    pins.update(hashes(sources))
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / 'inputs.json', pins)
    commands = []

    def run(command, name):
        command = list(map(str, command))
        commands.append(command)
        atomic_json(out / 'commands.json', commands)
        with (out / (name + '.log')).open('x') as log:
            subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           timeout=180, check=True)

    includes = [flag for x in ('include', 'src', 'src/ggml-cpu')
                for flag in ('-isystem', str(ggml / x))]
    run([cxx, '-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O3', '-UNDEBUG',
         '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-Wall', '-Wextra', '-Werror',
         *includes, '-c', HERE / 'native.cpp', '-o', out / 'native.o'], 'compile-test')
    run([cxx, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-static', out / 'native.o',
         candidate / 'candidate.o', *libs, '-lm', '-ldl', '-pthread',
         '-Wl,-Map=' + str(out / 'native.map'), '-o', out / 'native'], 'link')
    run([cc, '-march=rv64gc', '-mabi=lp64d', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
         HERE / 'init.c', '-o', out / 'init'], 'compile-init')
    run([objdump, '-d', '--disassemble=ggml_quantize_mat_q8_K_4x1_ara_generic', out / 'native'], 'oracle-disasm')
    if 'fmadd.s' not in (out / 'oracle-disasm.log').read_text():
        raise ValueError('Generic quantizer FMA contract differs')
    entries = ['dir /dev 755 0 0', 'nod /dev/console 600 0 0 c 5 1',
               f'file /init {out / "init"} 755 0 0', f'file /native {out / "native"} 755 0 0',
               f'file /captures.txt {captures / "captures.txt"} 444 0 0']
    entries += [f'file /{path.name} {path} 444 0 0' for path in capture_files if path.suffix == '.bin']
    listing = out / 'initramfs.list'
    listing.write_text('\n'.join(entries) + '\n')
    with (out / 'initramfs.cpio').open('xb') as stream:
        subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Build input drift')
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out / 'manifest.json', pins)
    atomic_json(out / 'build.json', dict(state='READY', execution='NOT_RUN',
        manifest_sha256=digest(out / 'manifest.json'), binary_sha256=digest(out / 'native'),
        scope='Actual combined-Zvfh Q8_K production selector versus generic; functional only'))


if __name__ == '__main__':
    main()
