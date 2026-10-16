"""Legal non-overlapping widening/narrowing groups, with independent integers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS=['vwaddu.vv','vwadd.vv','vwsubu.vv','vwsub.vv','vwmulu.vv','vwmul.vv',
     'vwmulsu.vv','vzext.vf2','vsext.vf2','vnsrl.wv','vnsra.wv','vnclipu.wv','vnclip.wv']

def shapes():
    return [(s,l) for s,l in build.shapes() if s<64 and l!='m8']

def assembly(sew,lmul):
    double=build.LMULS[[x[0] for x in build.LMULS].index(lmul)+1][0]
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,op in enumerate(OPS):
        lines += [f'.global op_{i}',f'op_{i}:','csrr t4,vxrm','csrr t5,vxsat',
                  'csrw vxrm,a7','csrwi vxsat,0']
        if i<9:
            lines += [f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                      f'vle{sew}.v v8,(a0)',f'vle{sew}.v v16,(a1)',
                      f'vsetvli t0,a4,e{2*sew},{double},tu,mu',
                      f'vle{2*sew}.v v24,(a2)','vlm.v v0,(a5)',
                      f'vsetvli t0,a3,e{2*sew if i>=7 else sew},{double if i>=7 else lmul},tu,mu']
            lines += [f'{op} v24,v8'+(',v16' if i<7 else '')+',v0.t']
        else:
            lines += [f'vsetvli t0,a4,e{2*sew},{double},tu,mu',
                      f'vle{2*sew}.v v8,(a0)',f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                      f'vle{sew}.v v16,(a1)',f'vle{sew}.v v24,(a2)',
                      'vlm.v v0,(a5)',f'vsetvli t0,a3,e{sew},{lmul},tu,mu',
                      f'{op} v24,v8,v16,v0.t']
        lines += ['csrr a0,vstart','csrr t1,vxsat','slli t1,t1,32','or a0,a0,t1',
                  'csrw vxrm,t4','csrw vxsat,t5',
                  f'vsetvli t0,a4,e{2*sew if i<9 else sew},{double if i<9 else lmul},tu,mu',
                  f'vse{2*sew if i<9 else sew}.v v24,(a2)','ret']
    return '\n'.join(lines)+'\n'

def run(out,cross):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('width_oracle.c')
    manifest=dict(scope='Widening/narrowing non-overlap, four vxrm, vxsat, vstart=0',
                  cases=[],operations=OPS,restart_tested=False,
                  exclusions=['SEW64 widening exceeds ELEN64','m8 widening exceeds EMUL8',
                              'No legal-overlap variant or vf4/vf8 extension yet'])
    for sew,lmul in shapes():
        name=f'rvv_widths_e{sew}_{lmul}'
        asm=out/(name+'.S');asm.write_text(assembly(sew,lmul))
        (out/'operations.h').write_text('\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,long,unsigned long);'%i for i in range(len(OPS)))+
                          '\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(len(OPS)))+'\n')
        binary=binaries/name
        command=[cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
                 '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
                 '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
                 '-Wall','-Wextra','-Werror',f'-DSEW={sew}','-I'+str(out),
                 str(source),str(asm),'-lgcc','-o',str(binary)]
        subprocess.run(command,check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_WIDTH_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),
                       stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);a=p.parse_args();run(a.out,a.cross)
