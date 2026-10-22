"""Whole register loads/stores/moves independent of ordinary VL and VILL."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

OPS=[(n,e) for n in (1,2,4,8) for e in (8,16,32,64)]+[(n,0) for n in (1,2,4,8)]

def assembly():
    lines=['.text']
    for i,(n,e) in enumerate(OPS):
        lines += [f'.global op_{i}',f'op_{i}:','csrwi vstart,0',
                  'vl8re8.v v8,(a0)','vl8re8.v v24,(a1)',
                  'beqz a3,config0_'+str(i),'li t0,1','beq a3,t0,config1_'+str(i),
                  'li t0,2','beq a3,t0,config2_'+str(i),'li t0,3','beq a3,t0,config3_'+str(i),
                  'li t0,1','slli t0,t0,63','vsetvl zero,zero,t0','j configured_'+str(i)]
        for mode,config in enumerate(('0,e8,m1','7,e16,m2','1,e32,m4','3,e64,m1')):
            lines += [f'config{mode}_{i}:',f'vsetivli zero,{config},tu,mu',f'j configured_{i}']
        lines += [f'configured_{i}:','csrw vstart,a2','csrr t3,vstart']
        if e:lines += [f'vl{n}re{e}.v v24,(a0)']
        else:lines += [f'vmv{n}r.v v24,v8']
        lines += ['csrr a0,vstart','slli t3,t3,32','or a0,a0,t3','csrwi vstart,0',f'vs{n}r.v v24,(a1)','ret']
    return '\n'.join(lines)+'\n'

def run(out,cross,detail=False):
    out.mkdir(parents=True,exist_ok=False);binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('whole_oracle.c');asm=out/'whole.S';asm.write_text(assembly())
    (out/'operations.h').write_text('\n'.join('extern unsigned long op_%d(const void *,void *,unsigned long,unsigned long);'%i for i in range(20))+
                                  '\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(20))+'\n')
    name='rvv_whole_registers'+('_detail' if detail else '');binary=binaries/name
    subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
        '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
        '-Wall','-Wextra','-Werror',f'-DDETAIL_BYTES={int(detail)}','-I'+str(out),str(source),str(asm),'-o',str(binary)],check=True)
    manifest=dict(scope='Whole NF1/2/4/8 EEW8/16/32/64 loads/stores and moves; VL/VILL/restart',
                  cases=[dict(name=name,sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                              pass_marker='RVV_WHOLE_PASS',timeout_seconds=180)],
                  exclusions=['Whole moves depend on SEW and are illegal under VILL; only loads/stores test VILL',
                              'vstart>EVL excluded: QEMU10.2 whole helper underflows its page length',
                              'vstart at or above largest representable VLMAX is excluded'],
                  source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__))})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('opt\nopt/ara-tests\nopt/ara-tests/'+name+'\n').encode(),
                       stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cross',required=True)
    p.add_argument('--detail',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.detail)
