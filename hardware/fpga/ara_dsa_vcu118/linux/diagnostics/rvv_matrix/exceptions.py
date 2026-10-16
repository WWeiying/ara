"""Guard-page tests isolated by process, not by skipping faulting instructions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def assembly(sew):
    lines=['.text','.global capacity','capacity:','li t0,-1',f'vsetvli a0,t0,e{sew},m1,tu,mu','ret']
    for ff in (0,1):
        lines += [f'.global load_{ff}',f'load_{ff}:',
                  f'vsetvli t0,a3,e{sew},m1,tu,mu',f'vle{sew}.v v24,(a1)',
                  'vlm.v v0,(a2)',f'vle{sew}'+('ff' if ff else '')+'.v v24,(a0),v0.t',
                  'csrr a0,vl','csrr t1,vstart','slli t1,t1,32','or a0,a0,t1',
                  f'vsetvli t0,a3,e{sew},m1,tu,mu',f'vse{sew}.v v24,(a1)','ret']
    return '\n'.join(lines)+'\n'

def run(out,cross,detail=False):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('exception_oracle.c')
    manifest=dict(scope='Protected-page mask suppression and fault-only-first, isolated child processes',
                  cases=[],operations=['vle.v','vleff.v'],
                  exclusions=['No indexed overlap replay repair','No misaligned/segment fault replay'])
    for sew in (8,16,32,64):
        name=f'rvv_exceptions{"_detail" if detail else ""}_e{sew}';asm=out/(name+'.S');asm.write_text(assembly(sew))
        binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DDETAIL_SCENARIOS={int(detail)}',str(source),str(asm),'-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_EXCEPTION_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cross',required=True)
    p.add_argument('--detail',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.detail)
