#!/usr/bin/env python3
"""Cross-link isolated stage-one replays from accepted, pinned backend archives."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FROZEN = OUT/'fpga_unified_20261108_02'
REPLAY = Path('/home/wangwy/fpga_runs/qbs_akv_mechanism_stage1_20261108_01/build_02')
TOOLS = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin')


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    require(out.parent == OUT and not out.exists(), 'Fresh verification output required')
    pins = json.loads((REPLAY/'source-pins.json').read_text())
    for name, digest in pins.items():
        require(sha(name) == digest, 'Replay input drift: '+name)
    out.mkdir()
    commands = []

    def run(argv, cwd=None):
        argv = [str(x) for x in argv]
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=600)
        commands.append(dict(argv=argv, cwd=str(cwd) if cwd else None,
                             returncode=r.returncode, stdout=r.stdout, stderr=r.stderr))
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        require(r.returncode == 0, 'Command failed: '+r.stderr[-4000:])
        return r.stdout

    result = dict(state='FAIL', board_executed=False, rtl_modified=False)
    try:
        probe = HERE/'node_probe'
        for f in [Path(__file__), HERE/'prepare_replay.py', probe/'prepare.py',
                  probe/'node_probe.c', probe/'node_probe.h', FROZEN/'build/compile_commands.json']:
            pins[str(f)] = sha(f)
        source = FROZEN/'inputs/llama/ggml/src/ggml-cpu/ggml-cpu.c'
        run([sys.executable, probe/'prepare.py', '--source', source, '--output', out/'cpu'])
        run([sys.executable, HERE/'prepare_replay.py', '--source', REPLAY/'inputs/replay_main.cpp',
             '--output', out/'frontend'])
        for name in ('path_counts.cpp', 'path_counts.hpp', 'history.txt', 'prompt_qwen.txt'):
            shutil.copy2(REPLAY/'inputs'/name, out/'frontend'/name)
        libs = []
        for name in ('libllama.a','libggml.a','libggml-cpu.a','libggml-base.a'):
            target = out/name
            shutil.copy2(REPLAY/'inputs'/name, target)
            libs.append(target)
        rows = json.loads((FROZEN/'build/compile_commands.json').read_text())
        rows = [r for r in rows if r['file'] == str(source)]
        require(len(rows) == 1, 'Missing unique CPU compile recipe')
        row = rows[0]
        argv = shlex.split(row['command'])
        argv[argv.index(str(source))] = str(out/'cpu/ggml-cpu.c')
        dst = argv.index('-o')+1
        argv[dst] = str(out/'cpu-off.o')
        run(argv, row['directory'])
        require(sha(out/'cpu-off.o') == sha(Path(row['directory'])/row['output']),
                'Macro-disabled CPU object does not match accepted original')
        argv[dst] = str(out/'ggml-cpu.c.o')
        run([*argv, '-DGGML_STAGE1_NODE_NS'], row['directory'])
        cflags = ['-std=gnu11','-O2','-march=rv64gcv','-mabi=lp64d',
                  '-fno-tree-vectorize','-fno-tree-slp-vectorize',
                  '-Wall','-Wextra','-Werror','-I'+str(out/'cpu')]
        run([TOOLS/'riscv64-linux-gcc', *cflags, '-c',out/'cpu/node_probe.c','-o',out/'node_probe.o'])
        probe_lib = out/'libggml-cpu-probe.a'
        shutil.copy2(libs[2], probe_lib)
        run([TOOLS/'riscv64-linux-ar', 'r', probe_lib, out/'ggml-cpu.c.o'])
        names = run([TOOLS/'riscv64-linux-ar','t',probe_lib]).splitlines()
        require(names.count('ggml-cpu.c.o') == 1, 'CPU archive replacement ambiguous')
        common = ['-std=c++17','-march=rv64gcv','-mabi=lp64d','-O3',
                  '-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror',
                  '-I'+str(out/'cpu'),'-I'+str(out/'frontend')]
        common += ['-I'+str(FROZEN/'inputs/llama'/d) for d in ('include','ggml/include','vendor')]
        for name in ('replay_plain','replay_probe','path_counts'):
            run([TOOLS/'riscv64-linux-g++',*common,'-c',out/'frontend'/(name+'.cpp'),'-o',out/(name+'.o')])
        original = json.loads((REPLAY/'commands.json').read_text())
        link = [r['argv'] for r in original if any(x.startswith('-Wl,--wrap=') for x in r['argv'])]
        require(len(link) == 1, 'Missing unique original wrapper link')
        wraps = [x for x in link[0] if x.startswith('-Wl,--wrap=')]
        for mode in ('plain','probe'):
            elf = out/('stage1-'+mode)
            run([TOOLS/'riscv64-linux-g++','-march=rv64gcv','-mabi=lp64d','-O3','-static',
                 out/('replay_'+mode+'.o'),out/'path_counts.o',
                 *([out/'node_probe.o'] if mode=='probe' else []), *wraps,
                 '-o',elf,libs[0],libs[1],'-ldl',probe_lib if mode=='probe' else libs[2],libs[3],'-lm'])
            header = run([TOOLS/'riscv64-linux-readelf','-h','-l','-A',elf])
            require('INTERP' not in header and 'RISC-V' in header, 'Wrong ELF target/linkage')
        for name, digest in pins.items():
            require(sha(name) == digest, 'Input changed while compiling: '+name)
        result.update(state='CROSS_LINKED_BOARD_UNTESTED', macro_off_object_identical=True,
                      elfs={mode:sha(out/('stage1-'+mode)) for mode in ('plain','probe')},
                      measurement_acceptance=False, model_executed=False)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    except BaseException as e:
        result['error'] = repr(e)
        raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
