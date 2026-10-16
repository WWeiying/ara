"""Independent indexed EEWs and ordered duplicate-store semantics."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build


def operations(sew,lmul):
    lmuls=[x[0] for x in build.LMULS]
    base=lmuls.index(lmul)
    result=[]
    for index_sew in (8,16,32,64):
        delta=index_sew.bit_length()-sew.bit_length()
        index=base+delta
        if 0<=index<len(lmuls):
            for mode in range(5):result.append((index_sew,lmuls[index],mode))
    return result


def assembly(sew,lmul,restart=False):
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,(index_sew,index_lmul,mode) in enumerate(operations(sew,lmul)):
        store=mode>=2
        insn=('vsoxei' if mode>=3 else 'vsuxei') if store else ('vloxei' if mode else 'vluxei')
        lines += [f'.global op_{i}',f'op_{i}:',f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vle{sew}.v v24,('+('a0' if store else 'a1')+')',
                  f'vsetvli t0,a4,e{index_sew},{index_lmul},tu,mu',
                  f'vle{index_sew}.v v8,(a2)','vlm.v v0,(a5)',
                  f'vsetvli t0,a3,e{sew},{lmul},tu,mu']
        if restart:lines += ['csrw vstart,a6']
        lines += [
                  f'{insn}{index_sew}.v v24,('+('a1' if store else 'a0')+'),v8,v0.t',
                  'csrr t4,vstart']
        if not store:lines += [f'vsetvli t0,a4,e{sew},{lmul},tu,mu',f'vse{sew}.v v24,(a1)']
        lines += ['mv a0,t4','ret']
    return '\n'.join(lines)+'\n'


def run(out,cross,restart=False):
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('index_width_oracle.c')
    manifest=dict(scope='Independent index EEW8/16/32/64, ordered/unordered and ordered duplicates, '+('nonzero restart' if restart else 'vstart=0'),
        cases=[],exclusions=['Illegal index EMUL outside 1/8..8 is excluded',
                            'EEW8 index domain caps VL to keep byte offsets representable',
                            'Resident non-overlapping buffers; fault/segment cases separate'])
    manifest['restart_tested']=restart
    if restart:
        manifest['restart_points']=['one','half_vl','vl_if_representable','last_capacity_element']
        manifest['trace']='28 drained first-indexed-load boundaries per ELF'
    for sew,lmul in build.shapes():
        ops=operations(sew,lmul);count=len(ops)
        name=f'rvv_index_width'+('_restart' if restart else '')+f'_e{sew}_{lmul}'
        asm=out/(name+'.S');asm.write_text(assembly(sew,lmul,restart))
        header='\n'.join('extern unsigned long op_%d(const void *,void *,const void *,unsigned long,unsigned long,const void *,unsigned long);'%i for i in range(count))
        header+='\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(count))
        header+='\n#define INDEX_SEWS '+','.join(str(s) for s,_,_ in ops)
        header+='\n#define MODES '+','.join(str(m) for _,_,m in ops)
        header+=f'\n#define OP_COUNT {count}\n'
        (out/'operations.h').write_text(header)
        binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DRESTART_INDEX_WIDTHS={int(restart)}','-I'+str(out),str(source),str(asm),'-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,index_sews=sorted({s for s,_,_ in ops}),
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),pass_marker='RVV_INDEX_WIDTH_PASS',timeout_seconds=600 if restart else 180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],input=('\n'.join(entries)+'\n').encode(),
                       stdout=stream,cwd=out/'overlay',check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cross',required=True)
    p.add_argument('--restart',action='store_true')
    a=p.parse_args();run(a.out,a.cross,a.restart)
