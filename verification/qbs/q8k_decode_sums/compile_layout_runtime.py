#!/usr/bin/env python3
"""Build both complete GGML quantizer translation units without modifying runtime."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use verification/out')
    out.mkdir(parents=True, exist_ok=False)
    source = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quants.c')
    database = ROOT/'verification/out/q8k-model-off-on-20261026-01/libraries/compile_commands.json'
    rows = [row for row in json.loads(database.read_text()) if Path(row['file']).resolve() == source]
    if len(rows) != 1:
        raise ValueError('Expected one production compile record')
    command = shlex.split(rows[0]['command'])
    if [x for x in command if x.startswith('-march=')][-1:] != ['-march=rv64gcv_zfh_zvfh']:
        raise ValueError('Unexpected effective ISA')
    text = source.read_text()
    start = text.index('void quantize_row_q8_K(')
    end = text.index('//===================================== Dot products', start)
    body = text[start:end]
    first = body.index('            // first iteration clear')
    last = body.index('            rem -= vl;', first)
    candidate = body[:first] + '            qbs_decode_sums_layout_candidate(v_q, vl, y_block->bsums + offset/16);\n' + body[last:]
    zero = '        vint16m1_t v_zero_sum = __riscv_vmv_v_x_i16m1(0, 1);\n'
    if candidate.count(zero) != 1:
        raise ValueError('Quantizer structure drift')
    candidate = candidate.replace(zero, '')
    generated = out/'candidate.c'
    generated.write_text('#if defined(__riscv_v)\n#include "'+str(HERE/'sums_layout.h')+'"\n#endif\n' +
                         text[:start] + candidate + text[end:])
    inputs = {source, database, generated, HERE/'sums_layout.h', Path(__file__), Path(command[0]).resolve()}
    for directory in {Path(x[2:]).resolve() for x in command if x.startswith('-I')}:
        inputs.update(p for p in directory.rglob('*') if p.is_file() and p.suffix in {'.h','.hpp','.inc','.inl'})
    pins = hashes(inputs)
    atomic_json(out/'inputs.json', pins)
    result = dict(state='RUNNING', production_modified=False, numerical_validation=False,
                  performance_validation=False, objects={})
    try:
        for name, path in (('original', source), ('candidate', generated)):
            argv = list(command)
            argv[argv.index('-c')+1] = str(path)
            argv[argv.index('-o')+1] = str(out/(name+'.o'))
            argv += ['-iquote', str(source.parent)]
            atomic_json(out/(name+'.command.json'), argv)
            with (out/(name+'.log')).open('x') as stream:
                subprocess.run(argv, cwd=rows[0]['directory'], stdout=stream,
                               stderr=subprocess.STDOUT, check=True, timeout=180)
            result['objects'][name] = digest(out/(name+'.o'))
        if hashes(map(Path, pins)) != pins:
            raise ValueError('Input drift')
        result.update(state='COMPILE_ONLY_PASS', inputs_sha256=digest(out/'inputs.json'))
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        atomic_json(out/'result.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
