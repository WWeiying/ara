#!/usr/bin/env python3
"""Archive tested external sources without committing or modifying llama.cpp."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
RUNTIME=Path('/home/wangwy/llama/llama.cpp').resolve()


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Fresh verification output required')
    receipt=ROOT/'verification/out/m4-sums-models-20261029-01/result.json'
    accepted=json.loads(receipt.read_text())
    if accepted['state']!='PASS' or not accepted['pipeline_pins_match']:
        raise ValueError('Model campaign not accepted')
    stage=accepted['stages']['libraries'];directory=Path(stage['directory'])
    if digest(directory/'result.json')!=stage['result_sha256']:
        raise ValueError('Library receipt identity')
    library=json.loads((directory/'result.json').read_text())
    if library['state']!='PASS' or not library['post_pins_match'] or \
       digest(directory/'source-pins.json')!=library['source_pins_sha256']:
        raise ValueError('Library source inventory identity')
    pins=json.loads((directory/'source-pins.json').read_text())
    selected={}
    for name,expected in pins.items():
        source=Path(name)
        if source.is_relative_to(RUNTIME) and source.suffix in ('.c','.cpp','.h','.hpp','.txt','.cmake'):
            if not source.is_file() or digest(source)!=expected:
                raise ValueError('Tested runtime source changed: '+name)
            selected[source]=expected
    if not selected:raise ValueError('Empty runtime inventory')
    def git(*args):
        return subprocess.check_output(['git','-C',str(RUNTIME),*args],timeout=60)
    head=git('rev-parse','HEAD');status=git('status','--porcelain','--untracked-files=no')
    patch=git('diff','--binary','HEAD')
    out.mkdir()
    for source in selected:
        target=out/'runtime'/source.relative_to(RUNTIME)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        if digest(target)!=selected[source]:raise ValueError('Snapshot copy differs')
    (out/'runtime-head.txt').write_bytes(head)
    (out/'runtime-status.txt').write_bytes(status)
    (out/'runtime-working-tree.patch').write_bytes(patch)
    for source,expected in selected.items():
        if digest(source)!=expected:raise ValueError('Runtime changed during snapshot')
    if git('rev-parse','HEAD')!=head or git('diff','--binary','HEAD')!=patch or \
       git('status','--porcelain','--untracked-files=no')!=status:
        raise ValueError('Runtime worktree changed during snapshot')
    result=dict(state='TESTED_RUNTIME_SOURCE_SNAPSHOT',source_count=len(selected),
        runtime_head=head.decode().strip(),external_worktree_modified=False,
        note='Patch includes all preexisting tracked differences, not an ownership claim. '
             'Pinned source copies also retain consumed ignored/untracked headers. '
             'This is a source archive, not a new build or model test.',
        source_hashes={str(source.relative_to(RUNTIME)):expected for source,expected in selected.items()},
        evidence={str(receipt):digest(receipt),str(directory/'result.json'):digest(directory/'result.json'),
                  str(directory/'source-pins.json'):digest(directory/'source-pins.json'),
                  str(Path(__file__).resolve()):digest(Path(__file__))},
        artifacts={str(f.relative_to(out)):digest(f) for f in out.rglob('*') if f.is_file()})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['state'],len(selected),head.decode().strip())


if __name__=='__main__':main()
