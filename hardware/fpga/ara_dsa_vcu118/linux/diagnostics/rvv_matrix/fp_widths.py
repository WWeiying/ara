"""FP32/64 widening/narrowing and fixed-ROD conversions using SoftFloat."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import floating


def shapes(sew=32):
    return [l for s,l in build.shapes() if s==sew and l!='m8']


def assembly(lmul,sew=32):
    double=build.LMULS[[x[0] for x in build.LMULS].index(lmul)+1][0]
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,op in enumerate(('vfwcvt.f.f.v','vfncvt.f.f.w','vfncvt.rod.f.f.w')):
        src,dst=(sew,sew*2) if i==0 else (sew*2,sew)
        srclmul=lmul if i==0 else double
        dstlmul=double if i==0 else lmul
        lines += [f'.global op_{i}',f'op_{i}:','csrr t4,frm','csrr t5,fflags',
                  f'vsetvli t0,a4,e{src},{srclmul},tu,mu',f'vle{src}.v v8,(a0)',
                  f'vsetvli t0,a4,e{dst},{dstlmul},tu,mu',f'vle{dst}.v v24,(a1)',
                  'vlm.v v0,(a2)',f'vsetvli t0,a3,e{sew},{lmul},tu,mu',
                  'csrw frm,a5','csrw fflags,a6',f'{op} v24,v8,v0.t',
                  'csrr a0,vstart','csrr t1,fflags','slli t1,t1,32','or a0,a0,t1',
                  'csrw frm,t4','csrw fflags,t5',f'vsetvli t0,a4,e{dst},{dstlmul},tu,mu',
                  f'vse{dst}.v v24,(a1)','ret']
    return '\n'.join(lines)+'\n'


def run(out,cross,softfloat,half=False):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('fp_width_oracle.c')
    adapter=Path(__file__).with_name('fp_width_fixture.c')
    sew=16 if half else 32
    (out/'config.h').write_text('/* Host reference: little endian. */\n')
    header='static const uint64_t input_bits[2][16]={'+','.join(
        '{'+','.join('UINT64_C(0x%x)'%x for x in floating.BITS[s])+'}' for s in (sew,sew*2))+'};\n'
    (out/'input_bits.h').write_text(header)
    host=out/'fp_width_fixture';sources=sorted(softfloat.glob('*.c'))
    subprocess.run(['gcc','-O2',f'-DSMALL_SEW={sew}','-I'+str(out),'-I'+str(softfloat),str(adapter),
                    *map(str,sources),'-o',str(host)],check=True)
    tables=json.loads(subprocess.check_output([str(host)]))
    (out/'fixtures.json').write_text(json.dumps(tables)+'\n')
    rows=['{'+','.join('{'+','.join('{UINT64_C(0x%x),%d}'%(bits,flags) for bits,flags in fixtures)+'}'
                      for fixtures in mode)+'}' for mode in tables]
    (out/'fixtures.h').write_text('static const struct fixture expected[5][3][32]={'+','.join(rows)+'};\n')
    (out/'operations.h').write_text('\n'.join(
        'extern unsigned long op_%d(const void *,void *,const void *,unsigned long,unsigned long,unsigned long,unsigned long);'%i
        for i in range(3))+'\n#define FUNCTIONS op_0,op_1,op_2\n')
    manifest=dict(scope=f'FP{sew}/{sew*2} width conversions, fixed ROD, flags, five frm, vstart=0',cases=[],
                  softfloat_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(softfloat.glob('*')) if p.suffix in ('.c','.h')},
                  exclusions=['FP conversion aliasing remains separate coverage'])
    for lmul in shapes(sew):
        name='rvv_fp_width_'+('e16_' if half else '')+lmul;asm=out/(name+'.S');asm.write_text(assembly(lmul,sew))
        binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSMALL_SEW={sew}','-I'+str(out),str(source),str(asm),'-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,lmul=lmul,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_FP_WIDTH_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (source,adapter,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),
                       stdout=stream,cwd=out/'overlay',check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--softfloat',type=Path,required=True)
    p.add_argument('--fp16',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.softfloat,a.fp16)
