"""Widening integer and FP reductions, with order-independent exact FP fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

def cases():
    integer=[('integer',s,l) for s,l in build.shapes() if s<64]
    fp=[('fp',s,l) for s,l in build.shapes() if s>=32]
    wide=[('fpwide',s,l) for s,l in build.shapes() if s==32]
    return integer+fp+wide

def assembly(kind,sew,lmul,operations=None):
    dest=sew if kind=='fp' else sew*2
    ops=['vwredsumu.vs','vwredsum.vs'] if kind=='integer' else (
        ['vfredosum.vs','vfredusum.vs','vfredmin.vs','vfredmax.vs'] if kind=='fp' else
        ['vfwredosum.vs','vfwredusum.vs'])
    if operations is not None:ops=operations
    lines=['.text','.global capacity','capacity:','li t0,-1',f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,op in enumerate(ops):
        lines += [f'.global op_{i}',f'op_{i}:',f'vsetvli t0,zero,e{dest},m1,tu,mu',
                  f'vle{dest}.v v16,(a1)',f'vle{dest}.v v24,(a2)',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',f'vle{sew}.v v8,(a0)',
                  'vlm.v v0,(a5)',f'vsetvli t0,a3,e{sew},{lmul},tu,mu']
        if kind!='integer':lines+=['csrr t4,frm','csrr t5,fflags','csrw frm,a6','csrwi fflags,0']
        lines += [f'{op} v24,v8,v16,v0.t','csrr a0,vstart']
        if kind!='integer':lines+=['csrr t1,fflags','slli t1,t1,32','or a0,a0,t1','csrw frm,t4','csrw fflags,t5']
        lines += [f'vsetvli t0,zero,e{dest},m1,tu,mu',f'vse{dest}.v v24,(a2)','ret']
    return '\n'.join(lines)+'\n'

def run(out,cross):
    out.mkdir(parents=True,exist_ok=False);binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('reduction_oracle.c')
    manifest=dict(scope='Widening integer, ordered/unordered FP and widening FP reductions, vstart=0',
                  cases=[],exclusions=['FP fixtures are positive dyadic exact sums, not tree-order rounding/NaN conformance'])
    for kind,sew,lmul in cases():
        dest=sew if kind=='fp' else sew*2
        count=4 if kind=='fp' else 2
        header=out/'operations.h';header.write_text('\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long);'%i for i in range(count))+
            '\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(count))+'\n')
        name=f'rvv_reduction_{kind}_e{sew}_{lmul}';asm=out/(name+'.S');asm.write_text(assembly(kind,sew,lmul))
        binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
            '-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
            f'-DSEW={sew}',f'-DDEST_SEW={dest}',f'-DFLOAT_REDUCTION={int(kind!="integer")}',
            f'-DOP_COUNT={count}','-I'+str(out),str(source),str(asm),'-lgcc','-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                                     pass_marker='RVV_REDUCTION_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cross',required=True)
    a=p.parse_args();run(a.out,a.cross)
