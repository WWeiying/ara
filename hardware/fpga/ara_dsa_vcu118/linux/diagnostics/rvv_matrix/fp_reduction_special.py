"""Ordered FP reduction special values/flags; unordered tree rounding stays separate."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import floating
import reductions

OPS=['vfredosum.vs','vfredmin.vs','vfredmax.vs']

def assembly(sew,lmul):
    return reductions.assembly('fp',sew,lmul,operations=OPS).replace('csrwi fflags,0','csrw fflags,a7')

def run(out,cross,softfloat,half=False):
    out.mkdir(parents=True,exist_ok=False);binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    here=Path(__file__).resolve().parent
    (out/'config.h').write_text('/* Host reference configuration: little endian. */\n')
    manifest=dict(scope='FP ordered sum/min/max, NaN/zero/infinity/subnormal/inexact, five frm and sticky flags',
                  cases=[],operations=OPS,restart_tested=False,
                  exclusions=['Unordered FP tree-rounding remains separate coverage'],
                  softfloat_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(softfloat.glob('*')) if p.suffix in ('.c','.h')})
    for sew in ((16,) if half else (32,64)):
        headers=out/f'e{sew}';headers.mkdir()
        (headers/'input_bits.h').write_text('static const uint64_t input_bits[16]={'+
            ','.join('UINT64_C(0x%x)'%x for x in floating.BITS[sew])+'};\n')
        host=headers/'fixture'
        adapter=headers/'adapter.o'
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-I'+str(headers),'-I'+str(out),
            '-I'+str(softfloat),'-c',str(here/'fp_reduction_fixture.c'),'-o',str(adapter)],check=True)
        subprocess.run(['gcc','-O2','-I'+str(out),'-I'+str(softfloat),str(adapter),
            *map(str,sorted(softfloat.glob('*.c'))),
            '-o',str(host)],check=True)
        for s,lmul in build.shapes():
            if s!=sew:continue
            name=f'rvv_fp_redspecial_e{sew}_{lmul}';directory=headers/lmul;directory.mkdir()
            _,num,den=next(x for x in build.LMULS if x[0]==lmul)
            caps=[vlen*num//(sew*den) for vlen in (512,1024)]
            tables=[json.loads(subprocess.check_output([str(host),str(sew),str(cap)])) for cap in caps]
            if any(len(table)!=3360 for table in tables):raise ValueError('Incomplete reduction fixtures')
            (directory/'fixtures.json').write_text(json.dumps(tables)+'\n')
            (directory/'fixtures.h').write_text('static const struct fixture fixtures[2][3360]={'+
                ','.join('{'+','.join('{UINT64_C(0x%x),%d}'%(bits,flags) for bits,flags in t)+'}' for t in tables)+'};\n')
            (directory/'operations.h').write_text('\n'.join(
                'extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);'%i
                for i in range(3))+'\n#define FUNCTIONS op_0,op_1,op_2\n')
            asm=directory/'operations.S';asm.write_text(assembly(sew,lmul));binary=binaries/name
            subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
                '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
                '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
                '-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DCAP512={caps[0]}',f'-DCAP1024={caps[1]}',
                '-I'+str(directory),'-I'+str(headers),str(here/'fp_reduction_oracle.c'),str(asm),'-o',str(binary)],check=True)
            manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
                sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                pass_marker='RVV_FP_REDSPECIAL_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__),here/'reductions.py',here/'floating.py',here/'fp_reduction_inputs.h',
         here/'fp_reduction_fixture.c',here/'fp_reduction_oracle.c')}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),
            stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--softfloat',type=Path,required=True)
    p.add_argument('--fp16',action='store_true');a=p.parse_args();run(a.out,a.cross,a.softfloat,a.fp16)
