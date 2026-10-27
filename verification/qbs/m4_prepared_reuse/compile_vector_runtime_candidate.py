#!/usr/bin/env python3
"""Compile the same private runtime hook with the accepted RVV byte-cache header."""
import argparse
import json
from pathlib import Path
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
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    original=ROOT/'verification/out/m4-runtime-candidate-compile-20261027-01'
    model=ROOT/'verification/out/m4-runtime-model-20261027-01'
    timing=ROOT/'verification/out/m4-vector-cache-soc-20261027-01'
    build=ROOT/'verification/out/m4-vector-cache-soc-build-20261027-01'
    pins={}
    for folder,name in ((original,'manifest.json'),(model,'manifest.json'),(timing,'source-pins.json'),(build,'manifest.json')):
        data=json.loads((folder/name).read_text())
        if hashes(map(Path,data))!=data:raise ValueError('Reviewed input drift: '+str(folder))
        receipt=folder/('build.json' if folder==build else 'result.json')
        pins.update(data);pins.update(hashes([folder/name,receipt]))
    if json.loads((original/'result.json').read_text())['state']!='COMPILE_ONLY_PASS' or any(
       json.loads((folder/'result.json').read_text())['state']!='PASS' for folder in (model,timing)):
        raise ValueError('Functional and timing acceptance required before integration')
    timing_report=json.loads((timing/'result.json').read_text())
    build_report=json.loads((build/'build.json').read_text())
    if timing_report['build']!=str(build) or timing_report['elf_sha256']!=build_report['elf_sha256']:
        raise ValueError('Timing evidence is not for this vector-cache build')
    pins.update(hashes([Path(__file__)]));out.mkdir(parents=True,exist_ok=False)
    for source,target in ((original/'repack.cpp',out/'repack.cpp'),
                          (HERE/'runtime_candidate.h',out/'runtime_candidate.h'),
                          (build/'value_cache.hpp',out/'value_cache.hpp')):
        shutil.copyfile(source,target)
    command=json.loads((original/'command.json').read_text())
    command[command.index('-c')+1]=str(out/'repack.cpp');command[command.index('-o')+1]=str(out/'candidate.o')
    atomic_json(out/'command.json',command)
    with (out/'compile.log').open('x') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    if hashes(map(Path,pins))!=pins:raise ValueError('Build source drift')
    pins.update(hashes([out/'repack.cpp',out/'runtime_candidate.h',out/'value_cache.hpp']))
    if result.returncode==0:pins.update(hashes([out/'candidate.o']))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'result.json',dict(state='COMPILE_ONLY_PASS' if result.returncode==0 else 'FAIL',
        returncode=result.returncode,runtime_modified=False,execution='NOT_RUN',
        delta='Same repack hook/controller, only cache byte operations use checked VLA RVV',
        manifest_sha256=digest(out/'manifest.json')))
    print(result.returncode);raise SystemExit(result.returncode)


if __name__=='__main__':main()
