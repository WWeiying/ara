"""Build only the private graph stimulus/init; link frozen candidate and archives."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))
from run_half_scale_soc import atomic_json, digest, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('Output must remain within graphs/')
    candidate = ROOT / 'verification/out/q8k-combined-zvfh-compile-20261026-02'
    production = ROOT / 'verification/out/grouped-pv-model-build-20261026-01'
    record = json.loads((candidate / 'result.json').read_text())
    pins = json.loads((candidate / 'inputs.json').read_text())
    if (record['state'] != 'COMPILE_ONLY_PASS' or
            record['effective_march'] != '-march=rv64gcv_zfh_zvfh' or
            record['inputs_sha256'] != digest(candidate / 'inputs.json') or
            record['object_sha256'] != digest(candidate / 'candidate.o') or
            hashes(map(Path, pins)) != pins):
        raise ValueError('Candidate identity drift')
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    ggml = Path('/home/wangwy/llama/llama.cpp/ggml')
    cxx, cc, objdump = [platform / ('tools/bin/riscv64-linux-' + name)
                        for name in ('g++', 'gcc', 'objdump')]
    libs = [production / ('llama/ggml/src/lib' + name + '.a')
            for name in ('ggml', 'ggml-cpu', 'ggml-base')]
    cpio = platform / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    sources = [*libs, cxx.resolve(), cc.resolve(), objdump.resolve(), cpio,
               candidate / 'candidate.o', candidate / 'inputs.json', candidate / 'result.json',
               *HERE.glob('*.py'), *HERE.glob('*.cpp'), HERE / 'init.c',
               HERE.parents[1] / 'ggml_m4_prepare_production/graph.cpp',
               HERE.parents[1] / 'ggml_tile_context/test.cpp',
               HERE.parents[1] / 'check_ggml_tile_context.py',
               HERE.parents[1] / 'test_ggml_tile_context.py',
               HERE.parents[1] / 'run_half_scale_soc.py',
               HERE.parents[1] / 'run_tile_context_engine.py',
               HERE.parents[1] / 'run_ggml_segmented.py']
    for lib in ('libstdc++.a', 'libgcc.a', 'libm.a', 'libc.a'):
        sources.append(Path(subprocess.check_output([cxx, '-print-file-name=' + lib], text=True).strip()).resolve())
    pins.update(hashes(sources))
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / 'inputs.json', pins)
    commands = []

    def run(command, label):
        command = list(map(str, command))
        commands.append(command)
        atomic_json(out / 'commands.json', commands)
        with (out / (label + '.log')).open('x') as stream:
            subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=180)

    includes = [flag for directory in ('include', 'src', 'src/ggml-cpu')
                for flag in ('-isystem', ggml / directory)]
    run([cxx, '-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O3', '-UNDEBUG',
         '-DGGML_USE_RISCV_QBS', '-DGGML_USE_RISCV_AKV', '-DGGML_USE_RISCV_QUANT_KV',
         '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-Wall', '-Wextra', '-Werror',
         *includes, '-I' + str(ROOT / 'software/qbs/include'), '-c', HERE / 'graph.cpp',
         '-o', out / 'graph.o'], 'compile-graph')
    run([cxx, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-static', out / 'graph.o',
         candidate / 'candidate.o', *libs, '-lm', '-ldl', '-pthread',
         '-Wl,-Map=' + str(out / 'graph.map'), '-o', out / 'graph'], 'link')
    run([cc, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
         HERE / 'init.c', '-o', out / 'init'], 'compile-init')
    for kind, type_id in (('q8_0', 8), ('q8_K', 15)):
        symbol = f'_Z19ggml_quantize_mat_tILl1EL9ggml_type{type_id}EEvPKfPvll'
        run([objdump, '-d', '--disassemble=' + symbol, out / 'graph'], kind + '-selector')
    q80 = (out / 'q8_0-selector.log').read_text()
    if '<ggml_quantize_mat_q8_0_4x1>' not in q80 or 'fprintf' in q80:
        raise ValueError('Q8_0 selector no longer directly uses the existing Zvfh implementation')
    listing = out / 'initramfs.list'
    listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n' +
                       f'file /init {out / "init"} 755 0 0\nfile /graph {out / "graph"} 755 0 0\n')
    with (out / 'initramfs.cpio').open('xb') as stream:
        subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Build input drift')
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out / 'manifest.json', pins)
    atomic_json(out / 'build.json', dict(state='READY', execution='NOT_RUN', graphs=384,
        q8k_calls_per_mode=52, q8_0_graphs=264, candidate_sha256=record['object_sha256'],
        graph_sha256=digest(out / 'graph'), manifest_sha256=digest(out / 'manifest.json'),
        scope='Combined full-GGML with unchanged scalar/decode oracle; awaiting parent run approval'))
    print(json.dumps(dict(state='READY', execution='NOT_RUN', output=str(out))))


if __name__ == '__main__':
    main()
