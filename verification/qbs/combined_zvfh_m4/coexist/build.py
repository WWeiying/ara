#!/usr/bin/env python3
"""Private combined-ISA graph suite linked to accepted production preparation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--signed-max', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use private verification/out')
    llama = Path('/home/wangwy/llama/llama.cpp')
    ggml = llama/'ggml'
    base = ROOT/'verification/out/q8k-model-off-on-20261026-01'
    accepted = ROOT/'verification/qbs/results/q8k-current-projection-acceptance-20261026.json'
    receipt = json.loads(accepted.read_text())
    obj = ROOT/'verification/out/q8k-combined-zvfh-integration-20261026-01/production.o'
    if receipt['state'] != 'PASS' or digest(obj) != receipt['production_object_sha256'] or \
            digest(ggml/'src/ggml-cpu/repack.cpp') != receipt['production_source_sha256']:
        raise ValueError('Accepted integrated preparation changed')
    candidate_pins = {}
    if args.signed_max:
        candidate = ROOT/'verification/out/q8k-signed-max-compile-20261026-01'
        gate = ROOT/'verification/qbs/results/q8k-signed-max-projection-20261026.json'
        numerical = ROOT/'verification/qbs/results/q8k-signed-max-quantizer-20261026.json'
        numerical_record = json.loads(numerical.read_text())
        if json.loads(gate.read_text())['state'] != 'PASS' or \
                numerical_record['state'] != 'FULL_QUANTIZER_REFERENCE_PASS':
            raise ValueError('Candidate numerical/performance prerequisite')
        candidate_pins = json.loads((candidate/'inputs.json').read_text())
        candidate_record = json.loads((candidate/'result.json').read_text())
        obj = candidate/'candidate.o'
        if candidate_record['state'] != 'COMPILE_ONLY_PASS' or \
                digest(obj) != candidate_record['object_sha256'] or \
                digest(obj) != numerical_record['candidate_object_sha256'] or \
                digest(candidate/'inputs.json') != candidate_record['inputs_sha256'] or \
                hashes(map(Path, candidate_pins)) != candidate_pins:
            raise ValueError('Candidate identity drift')
        candidate_pins.update(hashes([obj, gate, numerical, candidate/'inputs.json', candidate/'result.json']))
    result = json.loads((base/'result.json').read_text())
    manifest = base/'source-pins.json'
    if result['state'] != 'PASS' or digest(manifest) != result['source_pins_sha256']:
        raise ValueError('Model library receipt changed')
    oldpins = json.loads(manifest.read_text())
    libs = [base/('libraries/llama/ggml/src/lib'+name+'.a')
            for name in ('ggml', 'ggml-cpu', 'ggml-base')]
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    cxx, cc = [platform/('tools/bin/riscv64-linux-'+x) for x in ('g++', 'gcc')]
    cpio = platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    # Pin all currently consumed headers and the unchanged backend/SDK sources
    # against the accepted library build, not an unverified local archive.
    dependencies = list(ggml.rglob('*.h')) + list((ROOT/'software/qbs').rglob('*.h'))
    dependencies += list((ggml/'src').rglob('*.cpp')) + list((ggml/'src').rglob('*.c'))
    dependencies += list((ROOT/'software/qbs/src').glob('*.c'))
    for path in [*libs, *dependencies]:
        if path == ggml/'src/ggml-cpu/repack.cpp':
            continue  # supplied by the separately accepted object above
        if str(path) not in oldpins or digest(path) != oldpins[str(path)]:
            raise ValueError('Accepted library dependency mismatch: '+str(path))
    sources = [*libs, *dependencies, obj, accepted, base/'result.json', manifest,
               llama/'tests/test-ara-q4k-repack.cpp', HERE/'init.c', Path(__file__),
               ROOT/'verification/qbs/ggml_segmented_init.c', cxx.resolve(), cc.resolve(), cpio]
    pins = hashes(sources)
    pins.update(candidate_pins)
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    def run(command, label):
        command = list(map(str, command))
        commands.append(command)
        atomic_json(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
    includes = [flag for p in (ggml/'include', ggml/'src', ggml/'src/ggml-cpu', ROOT/'software/qbs/include')
                for flag in ('-I', p)]
    run([cxx, '-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O3', '-UNDEBUG',
         '-DGGML_TEST_RISCV_QBS', '-DGGML_USE_RISCV_QBS', '-fno-fast-math', '-ffp-contract=off',
         *includes, '-c', llama/'tests/test-ara-q4k-repack.cpp', '-o', out/'test.o'], 'compile')
    run([cxx, '-static', out/'test.o', obj, *libs, '-lm', '-ldl', '-pthread',
         '-Wl,-Map='+str(out/'link.map'), '-o', out/'test'], 'link')
    for suite, defines in [('context', []), ('alias', ['-DQBS_ALIAS']), ('barrier', ['-DQBS_BARRIER'])]:
        run([cc, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
             '-DQBS_CONTEXT', *defines, HERE/'init.c', '-o', out/('init-'+suite)], 'init-'+suite)
        listing = out/(suite+'.list')
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                           f'file /init {out/("init-"+suite)} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/(suite+'.cpio')).open('xb') as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Build input drift')
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out/'manifest.json', pins)
    atomic_json(out/'build.json', dict(state='READY', execution='NOT_RUN',
        manifest_sha256=digest(out/'manifest.json'), elf_sha256=digest(out/'test'),
        suites=['context', 'alias', 'barrier'], production_modified=False,
        signed_max_candidate=args.signed_max, quantizer_object=str(obj)))
    print(json.dumps(dict(state='READY', execution='NOT_RUN', output=str(out))))


if __name__ == '__main__':
    main()
