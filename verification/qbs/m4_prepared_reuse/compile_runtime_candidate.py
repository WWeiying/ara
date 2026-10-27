#!/usr/bin/env python3
"""Compile the actual GGML repack call-site candidate without modifying llama.cpp."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Fresh independent output required')
    source=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp')
    database=ROOT/'verification/out/q8k-model-off-on-20261026-01/libraries/compile_commands.json'
    records=[r for r in json.loads(database.read_text()) if Path(r['file']).resolve()==source]
    if len(records)!=1:raise ValueError('Expected unique production compile record')
    record=records[0];command=shlex.split(record['command'])
    pins=hashes([source,database,Path(__file__),HERE/'repack_candidate.patch',
        HERE/'runtime_candidate.h',HERE/'value_cache.hpp',ROOT/'software/qbs/ggml/m4-reuse-policy.h'])
    for directory in (Path('/home/wangwy/llama/llama.cpp/ggml'),ROOT/'software/qbs/ggml',ROOT/'software/qbs/include'):
        pins.update(hashes(directory.rglob('*.h')))
    pins.update(hashes([Path(command[0]).resolve()]))
    out.mkdir(parents=True,exist_ok=False)
    target=out/'repack.cpp';shutil.copyfile(source,target)
    subprocess.run(['git','apply','--recount',str(HERE/'repack_candidate.patch')],cwd=out,
        env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(out.parent)),check=True,timeout=30)
    command[command.index('-c')+1]=str(target);command[command.index('-o')+1]=str(out/'candidate.o')
    command+=['-iquote',str(source.parent),'-I'+str(HERE),'-I'+str(ROOT/'software/qbs/ggml')]
    atomic_json(out/'command.json',command)
    with (out/'compile.log').open('x') as f:
        result=subprocess.run(command,cwd=record['directory'],stdout=f,stderr=subprocess.STDOUT,timeout=180)
    state='COMPILE_ONLY_PASS' if result.returncode==0 else 'FAIL'
    if hashes(map(Path,pins))!=pins:raise ValueError('Source drift')
    pins.update(hashes([target]))
    if result.returncode==0:pins.update(hashes([out/'candidate.o']))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'result.json',dict(state=state,returncode=result.returncode,runtime_modified=False,
        candidate_source_sha256=digest(target),production_source_sha256=digest(source),
        execution='NOT_RUN',performance_measured=False,manifest_sha256=digest(out/'manifest.json')))
    print(state)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
