#!/usr/bin/env python3
"""Compile a private full production TU with only signed-max selection changed."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
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
    llama = Path('/home/wangwy/llama/llama.cpp')
    relative = Path('ggml/src/ggml-cpu/repack.cpp')
    header = Path('ggml/src/ggml-cpu/arch/riscv/q8_K-m4.h')
    if digest(llama/relative) != '4657efb9ed044846a8a4dd99748d774f3beb20a5177899f75e7705842928aa7a':
        raise ValueError('Integrated repack baseline changed')
    if digest(llama/header) != '9e13fd34bfe030bb14027994de18c53857ae0d05b0418e5795f4766ff6cbd368':
        raise ValueError('Quantizer baseline changed')
    database = ROOT/'verification/out/q8k-model-off-on-20261026-01/libraries/compile_commands.json'
    rows = [row for row in json.loads(database.read_text()) if Path(row['file']).resolve() == llama/relative]
    if len(rows) != 1: raise ValueError('Production compile record')
    command = shlex.split(rows[0]['command'])
    if [x for x in command if x.startswith('-march=')][-1:] != ['-march=rv64gcv_zfh_zvfh']:
        raise ValueError('Wrong effective ISA')
    if not all(x in command for x in ('-O3', '-DGGML_USE_RISCV_QBS', '-DGGML_USE_RISCV_AKV')):
        raise ValueError('Missing production options')
    out.mkdir(parents=True, exist_ok=False)
    (out/header).parent.mkdir(parents=True)
    shutil.copyfile(llama/relative, out/relative)
    shutil.copyfile(llama/header, out/header)
    helper = out/header.parent/'signed_max.h'
    shutil.copyfile(HERE/'signed_max.h', helper)
    subprocess.run(['git', 'apply', str(HERE/'quantizer.patch')], cwd=out,
                   env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(out.parent)),
                   check=True, capture_output=True)
    if (out/relative).read_bytes() != (llama/relative).read_bytes():
        raise ValueError('Unexpected dispatcher change')
    command[command.index('-c')+1] = str(out/relative)
    command[command.index('-o')+1] = str(out/'candidate.o')
    command += ['-iquote', str((llama/relative).parent)]
    sources = {llama/relative, llama/header, out/relative, out/header, helper,
               HERE/'signed_max.h', HERE/'quantizer.patch', Path(__file__), database,
               Path(command[0]).resolve()}
    for directory in {Path(x[2:]).resolve() for x in command if x.startswith('-I')}:
        sources.update(p for p in directory.rglob('*') if p.is_file() and p.suffix in {'.h','.hpp','.inc','.inl'})
    pins = hashes(sources)
    atomic_json(out/'inputs.json', pins)
    atomic_json(out/'command.json', command)
    with (out/'compile.log').open('x') as stream:
        process = subprocess.run(command, cwd=rows[0]['directory'], stdout=stream,
                                 stderr=subprocess.STDOUT, timeout=600)
    if hashes(map(Path, pins)) != pins: raise ValueError('Build input drift')
    result = dict(state='COMPILE_ONLY_PASS' if process.returncode == 0 else 'COMPILE_FAIL',
                  inputs_sha256=digest(out/'inputs.json'),
                  object_sha256=digest(out/'candidate.o') if process.returncode == 0 else None,
                  effective_march='-march=rv64gcv_zfh_zvfh', production_modified=False,
                  numerical_validation=False, performance_validation=False)
    atomic_json(out/'result.json', result)
    print(json.dumps(result))
    raise SystemExit(process.returncode)


if __name__ == '__main__':
    main()
