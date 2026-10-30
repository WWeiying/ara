#!/usr/bin/env python3
"""Mechanically promote the accepted private headers; preserve external dirty sources."""
import argparse
import json
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def replace(text,before,after,count):
    if text.count(before)!=count:raise ValueError('Reviewed header structure changed: '+before)
    return text.replace(before,after)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute-reviewed',action='store_true');a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent backup required')
    model=ROOT/'verification/out/m4-vector-runtime-model-20261027-01'
    accepted=ROOT/'verification/out/m4-vector-runtime-compile-20261027-01'
    pins=json.loads((model/'manifest.json').read_text())
    if json.loads((model/'result.json').read_text())['state']!='PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Final private model acceptance missing/drifted')
    public=ROOT/'software/qbs/ggml'
    live=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu')
    cache=(accepted/'value_cache.hpp').read_text()
    cache=replace(cache,'q8k_m4_experiment','ggml_riscv_q8_K_cache',2)
    controller=(accepted/'runtime_candidate.h').read_text()
    controller=replace(controller,'"value_cache.hpp"','"q8_K-prepared-cache.h"',1)
    controller=replace(controller,'q8k_m4_experiment','ggml_riscv_q8_K_cache',2)
    controller=replace(controller,'q8k_m4_runtime_candidate','ggml_riscv_q8_K_prepared',2)
    headers={'q8_K-prepared-cache.h':cache,'q8_K-prepared-reuse.h':controller,
             'm4-reuse-policy.h':(public/'m4-reuse-policy.h').read_text(),
             'rvv-byte-ops.h':(public/'rvv-byte-ops.h').read_text()}
    patch=(HERE/'repack_candidate.patch').read_text()
    patch=replace(patch,'"runtime_candidate.h"','"arch/riscv/q8_K-prepared-reuse.h"',1)
    patch=replace(patch,'q8k_m4_runtime_candidate::','ggml_riscv_q8_K_prepared::',3)
    for name,body in headers.items():
        for target in (public/name,live/'arch/riscv'/name):
            if target.exists() and target.read_text()!=body:raise ValueError('Refusing header overwrite: '+str(target))
    out.mkdir(parents=True,exist_ok=False)
    snapshot=out/'before';snapshot.mkdir()
    rebindings={}
    for relative in ('repack.cpp','arch/riscv/qbs.cpp','arch/riscv/qbs.h'):
        source=live/relative;target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        rebindings[str(source)]=dict(before_sha256=digest(source),snapshot=str(target),snapshot_sha256=digest(target))
    for name,body in headers.items():(out/name).write_text(body)
    (out/'repack.patch').write_text(patch)
    atomic_json(out/'source-snapshots.json',rebindings)
    if a.execute_reviewed:
        for name,body in headers.items():
            for target in (public/name,live/'arch/riscv'/name):
                if not target.exists():target.write_text(body)
    atomic_json(out/'result.json',dict(state='HEADERS_INSTALLED' if a.execute_reviewed else 'PREPARED_NOT_INSTALLED',
        algorithm_changed=False,changes='Namespace/include renaming only; repack patch not yet applied',
        headers=hashes(out/name for name in headers),source_snapshots=rebindings))
    print(json.dumps(dict(state='HEADERS_INSTALLED' if a.execute_reviewed else 'PREPARED',output=str(out))))


if __name__=='__main__':main()
