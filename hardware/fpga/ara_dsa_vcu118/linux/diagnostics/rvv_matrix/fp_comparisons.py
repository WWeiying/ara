"""Packed FP comparisons with independent SoftFloat boolean/flag fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import floating

OPS=[name+'.vv' for name in ('vmfeq','vmfne','vmflt','vmfle')]+[
    name+'.vf' for name in ('vmfeq','vmfne','vmflt','vmfle','vmfgt','vmfge')]


def assembly(sew,lmul,unmasked=False,destination='v24',restart=False,unboxed=False):
    if unboxed and sew not in (16,32):
        raise ValueError('Invalid scalar boxing requires FP16/32 within FLEN64')
    if restart and destination!='v24':
        raise ValueError('Restart/source-alias combinations need a separate oracle')
    if destination not in ('v24','v8','v16','v0'):
        raise ValueError('Unsupported comparison destination')
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,op in enumerate(OPS):
        lines += [f'.global op_{i}',f'op_{i}:','csrr t5,fflags',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vle{sew}.v v8,(a0)',f'vle{sew}.v v16,(a1)']
        if destination=='v24':lines += ['vlm.v v24,(a2)']
        lines += ['vlm.v v0,(a5)']
        if i>=4:
            if unboxed:
                lines += [('lhu' if sew==16 else 'lwu')+' t2,0(a1)',
                          'fmv.d.x ft0,t2']
            elif sew==16:
                lines += ['lhu t2,0(a1)','li t3,-1','slli t3,t3,16',
                          'or t2,t2,t3','fmv.d.x ft0,t2']
            else:
                lines += [('flw' if sew==32 else 'fld')+' ft0,0(a1)']
        lines += [f'vsetvli t0,a3,e{sew},{lmul},tu,mu','csrw fflags,a7']
        if restart:lines += ['csrw vstart,a6']
        lines += [
                  f'{op} {destination},v8,'+('v16' if i<4 else 'ft0')+('' if unmasked else ',v0.t'),
                  'csrr a0,vstart','csrr t1,fflags','slli t1,t1,32',
                  'or a0,a0,t1','csrw fflags,t5',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',f'vsm.v {destination},(a2)','ret']
    return '\n'.join(lines)+'\n'


def run(out,cross,softfloat,unmasked=False,destination='v24',restart=False,unboxed=False):
    if restart and destination!='v24':
        raise ValueError('Restart/source-alias combinations need a separate oracle')
    if destination not in ('v24','v8','v16','v0'):
        raise ValueError('Unsupported comparison destination')
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    fixture=Path(__file__).with_name('fp_compare_fixture.c')
    source=Path(__file__).with_name('fp_compare_oracle.c')
    (out/'config.h').write_text('/* Little-endian host reference. */\n')
    def words(values):return ','.join('UINT64_C(0x%x)'%x for x in values)
    (out/'compare_inputs.h').write_text('\n'.join(
        f'static const uint64_t raw{sew}[16]={{'+words(values)+'};'
        for sew,values in floating.BITS.items())+'\n')
    host=out/'fp_compare_fixture'
    subprocess.run(['gcc','-O2','-I'+str(out),'-I'+str(softfloat),
                    str(fixture),*map(str,sorted(softfloat.glob('*.c'))),
                    '-o',str(host)],check=True)
    manifest=dict(scope=('FP16/32 invalid scalar NaN boxes; ' if unboxed else 'FP16/32/64 ')+
                  'packed comparisons vv/vf; NaN, signed zero, sticky fflags, tu/mu; '+('nonzero restart' if restart else 'vstart=0'),
                  cases=[],operations=OPS,configurations_per_elf=17920*(4 if restart else 1),
                  input_rotations=32,initial_fflags=[0,1],restart_tested=restart,
                  unmasked=unmasked,destination=destination,
                  unboxed_scalar=unboxed,
                  exclusions=([] if restart else ['Nonzero vstart'])+
                  ([] if unboxed else ['Unboxed scalars'])+
                  ['All possible input bit patterns','Restart plus source aliases'],
                  softfloat_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(softfloat.glob('*')) if p.suffix in ('.c','.h')})
    if restart:
        manifest['restart_points']=['one','half_vl','vl','last_capacity_element']
        manifest['trace']='28 drained first-operation boundaries per ELF; not every trial'
    for sew in ((16,32) if unboxed else (16,32,64)):
        tables=json.loads(subprocess.check_output([str(host),str(sew)]))
        (out/f'fixtures_{sew}.json').write_text(json.dumps(tables)+'\n')
        directory=out/f'e{sew}';directory.mkdir()
        header='static const word inputs[16]={'+words(floating.BITS[sew])+'};\n'
        literal=','.join('{'+','.join('{'+','.join('{%d,%d}'%tuple(entry)
                   for entry in row)+'}' for row in table)+'}' for table in tables)
        header+='static const struct fixture expected[6][16][16]={'+literal+'};\n'
        (directory/'fixtures.h').write_text(header)
        (directory/'operations.h').write_text('\n'.join(
            'extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);'%i
            for i in range(len(OPS)))+'\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(len(OPS)))+'\n')
        for s,lmul in build.shapes():
            if s!=sew:continue
            suffix=('_restart' if restart else '')+('_unboxed' if unboxed else '')+('_unmasked' if unmasked else '')+('_alias_'+destination if destination!='v24' else '')
            name=f'rvv_fp_compare{suffix}_e{sew}_{lmul}';asm=out/(name+'.S')
            asm.write_text(assembly(sew,lmul,unmasked,destination,restart,unboxed));binary=binaries/name
            subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d',
                '-nostdlib','-static','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
                '-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',
                f'-DSEW={sew}',f'-DUNMASKED_COMPARISONS={int(unmasked)}',
                f'-DUNBOXED_COMPARISONS={int(unboxed)}',
                f'-DRESTART_COMPARISONS={int(restart)}',
                f'-DDESTINATION_KIND={ {"v24":0,"v8":1,"v16":2,"v0":3}[destination]}',
                '-I'+str(directory),str(source),str(asm),'-o',str(binary)],check=True)
            manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
                sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                pass_marker='RVV_FP_COMPARE_PASS',timeout_seconds=300))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,fixture,Path(__file__),Path(floating.__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+x['name'] for x in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(),stdout=stream,
                       cwd=out/'overlay',check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);p.add_argument('--softfloat',type=Path,required=True)
    p.add_argument('--unmasked',action='store_true')
    p.add_argument('--restart',action='store_true')
    p.add_argument('--unboxed',action='store_true')
    p.add_argument('--destination',choices=('v24','v8','v16','v0'),default='v24')
    a=p.parse_args();run(a.out,a.cross,a.softfloat,a.unmasked,a.destination,a.restart,a.unboxed)
