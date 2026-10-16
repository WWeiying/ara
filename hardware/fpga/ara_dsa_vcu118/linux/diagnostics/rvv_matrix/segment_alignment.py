"""Target-only misalignment probes with aligned staging and isolated children."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import extensions
import segments


def assembly(sew,lmul):
    regs=extensions.register_count(lmul)
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for op,(nf,mode) in enumerate((nf,mode) for nf in segments.fields(lmul) for mode in range(4)):
        store=mode%2;base=8 if store else 24
        lines += [f'.global op_{op}',f'op_{op}:',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'slli t1,a4,{(sew//8).bit_length()-1}',
                  'mv t2,a0' if store else 'mv t2,a1']
        for field in range(nf):
            lines += [f'vle{sew}.v v{base+field*regs},(t2)','add t2,t2,t1']
        lines += ['vlm.v v0,(a2)',f'vsetvli t0,a3,e{sew},{lmul},tu,mu',
                  'li t3,1','sd t3,0(a7)']
        opcode=('vssseg' if store else 'vlsseg') if mode>=2 else ('vsseg' if store else 'vlseg')
        lines += [f'{opcode}{nf}e{sew}.v v{base},(a5)'+(',a6' if mode>=2 else '')+',v0.t',
                  'csrr t4,vstart','li t3,2','sd t3,0(a7)']
        if not store:
            lines += [f'vsetvli t0,a4,e{sew},{lmul},tu,mu','mv t2,a1']
            for field in range(nf):
                lines += [f'vse{sew}.v v{base+field*regs},(t2)','add t2,t2,t1']
        lines += ['mv a0,t4','ret']
    return '\n'.join(lines)+'\n'


def run(out,cross):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('segment_alignment_oracle.c')
    manifest=dict(scope='NF3..8 unit/positive/negative stride target-only alignment capability; aligned preparation/readback, vstart=0',
                  diagnostic_only=True,cases=[],exclusions=['Indexed segments','Page faults','Nonzero restart','Exhaustive offsets'],
                  capability_exit_code=77,unexpected_no_active_traps_are_failures=True)
    for sew,lmul in build.shapes():
        nfs=segments.fields(lmul)
        if sew==8 or not nfs:continue
        directory=out/f'e{sew}_{lmul}';directory.mkdir()
        count=len(nfs)*4
        (directory/'operations.h').write_text('\n'.join(
            'extern unsigned long op_%d(const void *,void *,const void *,unsigned long,unsigned long,void *,long,void *);'%i
            for i in range(count))+'\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(count))+
            '\n#define FIELDS '+','.join(str(nf) for nf in nfs for _ in range(4))+f'\n#define OP_COUNT {count}\n')
        name=f'rvv_segment_alignment_e{sew}_{lmul}';asm=directory/'operations.S'
        asm.write_text(assembly(sew,lmul));binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={sew}','-I'+str(directory),
            str(source),str(asm),'-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,fields=nfs,
            configurations=len(nfs)*36*(2 if sew==16 else 3),diagnostic_only=True,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_SEGMENT_CAP_PASS',timeout_seconds=300))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,Path(__file__),Path(segments.__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(),stdout=stream,
                       cwd=out/'overlay',check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cross',required=True);a=p.parse_args();run(a.out,a.cross)
