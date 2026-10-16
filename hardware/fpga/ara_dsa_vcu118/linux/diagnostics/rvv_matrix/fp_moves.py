"""Bit-exact FP merge, broadcast, slide1 and scalar/vector transfer tests."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import floating

OPS=[('vfmerge.vfm','v24,v8,ft0,v0'),('vfmv.v.f','v24,ft0'),
     ('vfslide1up.vf','v24,v8,ft0,v0.t'),('vfslide1down.vf','v24,v8,ft0,v0.t'),
     ('vfslide1up.vf','v24,v8,ft0'),('vfslide1down.vf','v24,v8,ft0'),
     ('vfmv.s.f','v24,ft0'),('vfmv.f.s','ft1,v8')]


def assembly(sew,lmul,restart=False):
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,(opcode,args) in enumerate(OPS):
        lines += [f'.global op_{i}',f'op_{i}:','csrr t5,fflags',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',f'vle{sew}.v v8,(a0)',
                  f'vle{sew}.v v24,(a2)','vlm.v v0,(a5)','fld ft0,0(a1)',
                  f'vsetvli t0,a3,e{sew},{lmul},tu,mu']
        if restart:
            lines += ['srli t2,a6,32','csrw fflags,t2','slli t2,a6,32',
                      'srli t2,t2,32','csrw vstart,t2']
        else:lines += ['csrw fflags,a6']
        lines += [opcode+' '+args]
        if i==7:lines += ['fmv.x.d t2,ft1','sd t2,0(a7)']
        lines += ['csrr a0,vstart','csrr t1,fflags','slli t1,t1,32','or a0,a0,t1',
                  'csrw fflags,t5',f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vse{sew}.v v24,(a2)','ret']
    return '\n'.join(lines)+'\n'


def run(out,cross,restart=False,details=False,only=None,operations=None):
    operation_ids=list(range(len(OPS))) if operations is None else list(operations)
    if not operation_ids or len(set(operation_ids))!=len(operation_ids) or any(
            type(i) is not int or i<0 or i>=len(OPS) for i in operation_ids):
        raise ValueError('Operations must be distinct indices from 0 through 7')
    selected=[(s,l) for s,l in build.shapes() if s in (16,32,64)
              and (only is None or f'e{s}_{l}' in only)]
    if not selected:
        raise ValueError('No legal FP move shapes selected')
    if details and not restart:
        raise ValueError('Detailed supplement requires restart')
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('fp_move_oracle.c')
    manifest=dict(scope='Bit-exact FP16/32/64 merge/broadcast, masked/unmasked slide1, scalar/vector moves; tu/mu'+('; restart' if restart else '; vstart=0'),
                  cases=[],operations=OPS,restart_tested=restart,diagnostic_details=details,
                  restart_points=['one','half_vl','vl','last_capacity_element'] if restart else ['zero'],
                  exclusions=([] if restart else ['Nonzero restart'])+['Destination aliases','Physical fractional-group tails'],
                  scalar_patterns=16,vector_rotations=3,initial_fflags=[0,1])
    manifest['operation_ids']=operation_ids
    manifest['operation_partitioned']=operations is not None
    for sew in (16,32,64):
        directory=out/f'e{sew}';directory.mkdir()
        (directory/'inputs.h').write_text('static const word inputs[16]={'+
            ','.join('UINT64_C(0x%x)'%x for x in floating.BITS[sew])+'};\n')
        (directory/'operations.h').write_text('\n'.join(
            'extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,void *);'%i
            for i in range(len(OPS)))+'\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(len(OPS)))+'\n')
        for s,lmul in selected:
            if s!=sew:continue
            suffix='' if operations is None else '_ops'+ '-'.join(str(i) for i in operation_ids)
            name=f'rvv_fp_move'+('_restart' if restart else '')+('_detail' if details else '')+f'_e{sew}_{lmul}'+suffix;asm=out/(name+'.S')
            asm.write_text(assembly(sew,lmul,restart));binary=binaries/name
            subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d',
                '-nostdlib','-static','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
                '-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
                f'-DSEW={sew}',f'-DRESTART_MOVES={int(restart)}',f'-DDETAIL_MOVES={int(details)}',
                *([] if operations is None else [f'-DMOVE_OP_MASK={sum(1<<i for i in operation_ids)}']),
                '-I'+str(directory),str(source),str(asm),'-o',str(binary)],check=True)
            manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
                configurations=len(operation_ids)*3*16*(1 if sew==64 else 2)*7*4*2*(4 if restart else 1),
                operation_ids=operation_ids,
                scalar_boxing=['full_width'] if sew==64 else ['valid_box','invalid_box'],
                sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                pass_marker='RVV_FP_MOVE_PASS',timeout_seconds=300))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,Path(__file__),Path(floating.__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(),stdout=stream,
                       cwd=out/'overlay',check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--restart',action='store_true')
    p.add_argument('--diagnostic-details',action='store_true')
    p.add_argument('--only',nargs='+')
    p.add_argument('--operations',nargs='+',type=int)
    a=p.parse_args();run(a.out,a.cross,a.restart,a.diagnostic_details,a.only,a.operations)
