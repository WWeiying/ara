#!/usr/bin/env python3
"""Export only this promotion delta, never the external fork's unrelated edits."""
import argparse
import difflib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--promotion',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'software/qbs/integrations'):
        raise ValueError('Fresh scoped patch required')
    promotion=a.promotion.resolve(strict=True)
    snapshots=json.loads((promotion/'source-snapshots.json').read_text())
    llama=Path('/home/wangwy/llama/llama.cpp');cpu=llama/'ggml/src/ggml-cpu'
    patch=[];rebindings={}
    for relative in ('repack.cpp','arch/riscv/qbs.cpp','arch/riscv/qbs.h'):
        target=cpu/relative;record=snapshots[str(target)];before=Path(record['snapshot'])
        if digest(before)!=record['before_sha256']:raise ValueError('Before snapshot drift')
        repo_relative=str(target.relative_to(llama))
        patch.extend(difflib.unified_diff(before.read_text().splitlines(True),target.read_text().splitlines(True),
            fromfile='a/'+repo_relative,tofile='b/'+repo_relative))
        rebindings[str(target)]=dict(before_sha256=digest(before),after_sha256=digest(target),snapshot=str(before))
    headers=('q8_K-prepared-cache.h','q8_K-prepared-reuse.h','m4-reuse-policy.h','rvv-byte-ops.h')
    for name in headers:
        target=cpu/'arch/riscv'/name;canonical=ROOT/'software/qbs/ggml'/name
        if target.read_bytes()!=canonical.read_bytes() or target.read_bytes()!=(promotion/name).read_bytes():
            raise ValueError('Promoted header algorithm drift')
        patch.extend(difflib.unified_diff([],target.read_text().splitlines(True),
            fromfile='/dev/null',tofile='b/'+str(target.relative_to(llama))))
    out.write_text(''.join(patch))
    atomic_json(promotion/'installed-delta.json',dict(state='SCOPED_PATCH_EXPORTED',patch=str(out),patch_sha256=digest(out),
        rebindings=rebindings,headers=hashes(cpu/'arch/riscv'/name for name in headers),
        scope='Three existing files plus four new headers; excludes unrelated preexisting fork changes'))
    print(json.dumps(dict(patch=str(out),sha256=digest(out))))


if __name__=='__main__':main()
