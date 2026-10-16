"""Numerical memory tests on resident, aligned user buffers; no fault claim."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS=['unit_load','unit_store','stride_load','stride_store',
     'indexed_unordered_load','indexed_ordered_load','indexed_unordered_store',
     'indexed_ordered_store','segment2_load','segment2_store']

def assembly(sew,lmul,restart=False):
    lines=['.text','.global capacity','capacity:',
           'li t0,-1',f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for op in range(10):
        group=next(n for s,n,d in build.LMULS if s==lmul)
        lines += [f'.global op_{op}',f'op_{op}:',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vle{sew}.v v8,(a0)',f'vle{sew}.v v16,(a1)',
                  f'vle{sew}.v v24,(a2)','vlm.v v0,(a5)']
        if restart:lines += ['ld t4,0(sp)']
        if op==8 and group!=8:lines += [f'vle{sew}.v v{24+group},(a7)']
        if op==9 and group!=8:lines += [f'vle{sew}.v v{8+group},(a7)']
        lines += [f'vsetvli t0,a3,e{sew},{lmul},tu,mu']
        if restart:lines += ['csrw vstart,t4']
        if op==0:lines += [f'vle{sew}.v v24,(a0),v0.t']
        if op==1:lines += [f'vse{sew}.v v8,(a2),v0.t']
        if op==2:lines += [f'vlse{sew}.v v24,(a0),a6,v0.t']
        if op==3:lines += [f'vsse{sew}.v v8,(a2),a6,v0.t']
        if op==4:lines += [f'vluxei{sew}.v v24,(a0),v16,v0.t']
        if op==5:lines += [f'vloxei{sew}.v v24,(a0),v16,v0.t']
        if op==6:lines += [f'vsuxei{sew}.v v8,(a2),v16,v0.t']
        if op==7:lines += [f'vsoxei{sew}.v v8,(a2),v16,v0.t']
        if op>=8:
            if group==8:lines += ['li a0,-1','ret'];continue
            if op==8:
                lines += [f'vlseg2e{sew}.v v24,(a0),v0.t']
            else:
                lines += [f'vsseg2e{sew}.v v8,(a2),v0.t']
        lines += ['csrr a0,vstart',f'vsetvli t0,a4,e{sew},{lmul},tu,mu']
        if op in (0,2,4,5,8):lines += [f'vse{sew}.v v24,(a2)']
        if op==8:lines += [f'vse{sew}.v v{24+group},(a7)']
        lines += ['ret']
    return '\n'.join(lines)+'\n'

def run(out,cross,restart=False):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('memory_oracle.c')
    manifest=dict(scope='Resident aligned unit/stride/indexed/segment memory, masked, '+('nonzero restart' if restart else 'vstart=0'),
                  cases=[],operations=OPS,restart_tested=restart,
                  exclusions=['m8 segment2 illegal NFIELDS*EMUL>8',
                              'Indexed VL capped so byte offsets fit index EEW',
                              'No page faults, misalignment or zero-stride duplicate stores'])
    if restart:
        manifest['restart_points']=['one','half_vl','vl_if_representable','last_capacity_element']
        manifest['trace']='28 drained first-unit-load boundaries per ELF'
    for sew,lmul in build.shapes():
        name=f'rvv_memory'+('_restart' if restart else '')+f'_e{sew}_{lmul}'
        asm=out/(name+'.S');asm.write_text(assembly(sew,lmul,restart))
        header=out/'operations.h'
        header.write_text('\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,long,void *,unsigned long);'%i for i in range(10))+
                          '\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(10))+'\n')
        binary=binaries/name
        command=[cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib',
                 '-static','-ffreestanding','-fno-builtin','-fno-stack-protector',
                 '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
                 '-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
                 f'-DSEW={sew}',f'-DSEGMENT_ALLOWED={int(lmul!="m8")}',
                 f'-DRESTART_MEMORY={int(restart)}',
                 '-I'+str(out),str(source),str(asm),'-o',str(binary)]
        subprocess.run(command,check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_MEMORY_PASS',timeout_seconds=600 if restart else 180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(),stdout=stream,
                       cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--restart',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.restart)
