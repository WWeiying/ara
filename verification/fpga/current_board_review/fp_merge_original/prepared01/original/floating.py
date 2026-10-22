"""FP32/64 bit/flag fixtures from a pinned local Berkeley SoftFloat source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS=['vfadd.vv','vfsub.vv','vfmul.vv','vfdiv.vv','vfsqrt.v',
     'vfmacc.vv','vfmsac.vv','vfnmacc.vv','vfnmsac.vv',
     'vfcvt.x.f.v','vfcvt.xu.f.v','vfcvt.f.x.v','vfcvt.f.xu.v']
EXTRA_OPS=['vfcvt.rtz.x.f.v','vfcvt.rtz.xu.f.v','vfclass.v']
SCALAR_EXTRA_OPS=['vfrsub.vf','vfrdiv.vf','vfmin.vf','vfmax.vf',
                  'vfsgnj.vf','vfsgnjn.vf','vfsgnjx.vf']
DESTRUCTIVE_OPS=['vfmadd.vv','vfmsub.vv','vfnmadd.vv','vfnmsub.vv']
BITS={16:[0,0x8000,0x3c00,0xbc00,0x3800,0x4000,0x4200,0x1000,1,0x03ff,0x0400,
          0x7bff,0x7c00,0xfc00,0x7e55,0x7c55],
      32:[0,0x80000000,0x3f800000,0xbf800000,0x3f000000,0x40000000,0x40400000,
          0x33800000,1,0x007fffff,0x00800000,0x7f7fffff,0x7f800000,0xff800000,0x7fc12345,0x7f812345],
      64:[0,0x8000000000000000,0x3ff0000000000000,0xbff0000000000000,0x3fe0000000000000,
          0x4000000000000000,0x4008000000000000,0x3ca0000000000000,1,0x000fffffffffffff,
          0x0010000000000000,0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,
          0x7ff8123456789abc,0x7ff0123456789abc]}

def operations_for(extras=False,scalar_forms=False,scalar_extras=False,destructive=False):
    if destructive:return [op.replace('.vv','.vf') if scalar_forms else op for op in DESTRUCTIVE_OPS]
    if scalar_extras:return SCALAR_EXTRA_OPS
    return [OPS[i].replace('.vv','.vf') for i in (0,1,2,3,5,6,7,8)] if scalar_forms else OPS+(EXTRA_OPS if extras else [])


def assembly(sew,lmul,extras=False,scalar_forms=False,scalar_extras=False,unboxed=False,destructive=False):
    if unboxed and (not scalar_extras or sew==64):
        raise ValueError('Unboxed tests require FP16/32 scalar extras')
    scalar_forms=scalar_forms or scalar_extras
    lines=['.text','.global capacity','capacity:','li t0,-1',f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    operations=operations_for(extras,scalar_forms,scalar_extras,destructive)
    for i,op in enumerate(operations):
        lines += [f'.global op_{i}',f'op_{i}:','csrr t4,frm','csrr t5,fflags',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',f'vle{sew}.v v8,(a0)',
                  f'vle{sew}.v v16,(a1)',f'vle{sew}.v v24,(a2)','vlm.v v0,(a5)',
                  f'vsetvli t0,a3,e{sew},{lmul},tu,mu','csrw frm,a6','csrw fflags,a7']
        if scalar_forms:
            if unboxed:lines += [('lhu' if sew==16 else 'lwu')+' t2,0(a1)','fmv.d.x ft0,t2']
            elif sew==16:lines+=['lhu t2,0(a1)','li t3,-1','slli t3,t3,16','or t2,t2,t3','fmv.d.x ft0,t2']
            else:lines += [('flw' if sew==32 else 'fld')+' ft0,0(a1)']
            lines += [f'{op} v24,'+('v8,ft0' if not destructive and (scalar_extras or i<4) else 'ft0,v8')+',v0.t']
        else:lines += [f'{op} v24,v8'+(',v16' if i<4 or 5<=i<=8 else '')+',v0.t']
        lines += [
                  'csrr a0,vstart','csrr t1,fflags','slli t1,t1,32','or a0,a0,t1',
                  'csrw frm,t4','csrw fflags,t5',f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vse{sew}.v v24,(a2)','ret']
    return '\n'.join(lines)+'\n'

def run(out,cross,softfloat,extras=False,half=False,scalar_forms=False,scalar_extras=False,unboxed=False,destructive=False):
    if destructive and (extras or scalar_extras or unboxed):raise ValueError('Destructive FMA is a separate release')
    scalar_extras=scalar_extras or unboxed
    scalar_forms=scalar_forms or scalar_extras
    if extras and scalar_forms:raise ValueError('Scalar forms and extras are separate releases')
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('fp_oracle.c')
    adapter=Path(__file__).with_name('fp_fixture.c')
    (out/'config.h').write_text('/* Host reference configuration: little endian. */\n')
    host=out/'fp_fixture'
    sources=sorted(softfloat.glob('*.c'))
    operations=operations_for(extras,scalar_forms,scalar_extras,destructive)
    count=len(operations)
    subprocess.run(['gcc','-O2',f'-DOP_COUNT={count}',f'-DSCALAR_FORMS={int(scalar_forms)}',f'-DSCALAR_EXTRAS={int(scalar_extras)}',f'-DDESTRUCTIVE_FMA={int(destructive)}','-I'+str(out),'-I'+str(softfloat),str(adapter),
                    *map(str,sources),'-o',str(host)],check=True)
    manifest=dict(scope=('FP16' if half else 'FP32/64')+' five rounding modes, flags, nonfinite/subnormal, FMA/conversion; vstart=0',
                  cases=[],operations=operations,restart_tested=False,scalar_forms=scalar_forms,scalar_extras=scalar_extras,
                  unboxed_scalar=unboxed,
                  destructive_fma=destructive,
                  softfloat_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(softfloat.glob('*')) if p.suffix in ('.c','.h')},
                  exclusions=['Widen/narrow FP conversions','Reduction tree special values']+
                             ([] if half else ['FP16 uses a separate release']))
    for sew in ((16,) if half else (32,) if unboxed else (32,64)):
        scalar_indices=(4,1,14,15,13) if scalar_extras else (4,0,15)
        tables=([json.loads(subprocess.check_output([str(host),str(sew),str(14 if unboxed else index)])) for index in scalar_indices]
                if scalar_forms else json.loads(subprocess.check_output([str(host),str(sew)])))
        (out/f'fixtures_{sew}.json').write_text(json.dumps(tables)+'\n')
        header='static const word inputs[16]={'+','.join('UINT64_C(0x%x)'%x for x in BITS[sew])+'};\n'
        def rows(t):return ['{'+','.join('{'+','.join('{UINT64_C(0x%x),%d}'%(bits,flags) for bits,flags in fixtures)+'}' for fixtures in mode)+'}' for mode in t]
        literal=','.join('{'+','.join(rows(t))+'}' for t in tables) if scalar_forms else ','.join(rows(tables))
        header+=f'static const struct fixture expected'+(f'[{len(scalar_indices)}]' if scalar_forms else '')+f'[5][{count}][32]={{'+literal+'};\n'
        header_dir=out/f'e{sew}';header_dir.mkdir();(header_dir/'fixtures.h').write_text(header)
        for s,lmul in build.shapes():
            if s!=sew:continue
            suffix=('_destructive_scalar' if scalar_forms else '_destructive') if destructive else '_unboxed' if unboxed else '_scalar_extra' if scalar_extras else '_scalar' if scalar_forms else '_extra' if extras else ''
            name=f'rvv_fp{suffix}_e{sew}_{lmul}';asm=out/(name+'.S');asm.write_text(assembly(sew,lmul,extras,scalar_forms,scalar_extras,unboxed,destructive))
            (header_dir/'operations.h').write_text('\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);'%i for i in range(count))+
                '\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(count))+f'\n#define OP_COUNT {count}\n'+
                f'#define SCALAR_SEEDS {len(scalar_indices)}\n#define SCALAR_INDICES '+','.join(map(str,scalar_indices))+'\n')
            binary=binaries/name
            subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib',
                '-static','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
                '-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DSCALAR_FORMS={int(scalar_forms)}',
                '-I'+str(header_dir),str(source),str(asm),'-o',str(binary)],check=True)
            manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
                sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),pass_marker='RVV_FP_PASS',timeout_seconds=180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,adapter,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),stdout=stream,cwd=out/'overlay',check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--softfloat',type=Path,required=True)
    p.add_argument('--extras',action='store_true')
    p.add_argument('--fp16',action='store_true')
    p.add_argument('--scalar-forms',action='store_true')
    p.add_argument('--scalar-extras',action='store_true')
    p.add_argument('--unboxed',action='store_true')
    p.add_argument('--destructive-fma',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.softfloat,a.extras,a.fp16,a.scalar_forms,a.scalar_extras,a.unboxed,a.destructive_fma)
