"""Resident NF3..8 unit/strided segments with full-buffer scalar byte checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import extensions
import index_widths


def fields(lmul):
    regs = extensions.register_count(lmul)
    return [nf for nf in range(3, 9) if nf*regs <= 8]


def index_lmul(sew,lmul,index_sew=32):
    return next((group for width,group,_ in index_widths.operations(sew,lmul)
                 if width==index_sew),None)


def indexed_fields(sew,lmul,index_sew=32):
    if index_lmul(sew,lmul,index_sew) is None:return []
    return [nf for nf in range(2,9) if nf*extensions.register_count(lmul)<=8]


def assembly(sew, lmul, indexed=False, restart=False,index_sew=32):
    if index_sew not in (8,16,32,64):raise ValueError('Invalid index EEW')
    regs = extensions.register_count(lmul)
    lines = ['.text', '.global capacity', 'capacity:', 'li t0,-1',
             f'vsetvli a0,t0,e{sew},{lmul},tu,mu', 'ret']
    nfs=indexed_fields(sew,lmul,index_sew) if indexed else fields(lmul)
    for op, (nf, mode) in enumerate((nf, mode) for nf in nfs for mode in range(4)):
        store = mode % 2
        base = 8 if store else 24
        lines += [f'.global op_{op}', f'op_{op}:']
        if restart:lines += ['mv t5,a6']
        lines += [
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'slli t1,a4,{(sew//8).bit_length()-1}',
                  'mv a6,a0' if store else 'mv a6,a1']
        for field in range(nf):
            lines += [f'vle{sew}.v v{base+field*regs},(a6)', 'add a6,a6,t1']
        if indexed:
            lines += [f'vsetvli t0,a4,e{index_sew},{index_lmul(sew,lmul,index_sew)},tu,mu',
                      f'vle{index_sew}.v v16,(a5)',f'vsetvli t0,a4,e{sew},{lmul},tu,mu']
        lines += ['vlm.v v0,(a2)', f'vsetvli t0,a3,e{sew},{lmul},tu,mu']
        if restart:lines += ['csrw vstart,t5']
        if indexed:
            insn=('vsoxseg' if store else 'vloxseg') if mode>=2 else ('vsuxseg' if store else 'vluxseg')
            lines += [f'{insn}{nf}ei{index_sew}.v v{base},('+('a1' if store else 'a0')+'),v16,v0.t']
        else:
            insn = ('vssseg' if store else 'vlsseg') if mode >= 2 else ('vsseg' if store else 'vlseg')
            lines += [f'{insn}{nf}e{sew}.v v{base},('+('a1' if store else 'a0')+')'+
                      (',a5' if mode >= 2 else '')+',v0.t']
        lines += ['csrr t4,vstart']
        if not store:
            lines += [f'vsetvli t0,a4,e{sew},{lmul},tu,mu', 'mv a6,a1']
            for field in range(nf):
                lines += [f'vse{sew}.v v{base+field*regs},(a6)', 'add a6,a6,t1']
        lines += ['mv a0,t4', 'ret']
    return '\n'.join(lines)+'\n'


def run(out, cross, indexed=False, misaligned=False, restart=False,index_sew=32):
    if index_sew not in (8,16,32,64) or (not indexed and index_sew!=32):
        raise ValueError('Index EEW requires indexed mode and a legal width')
    if restart and misaligned:
        raise ValueError('Restart and target misalignment require separate diagnostics')
    out.mkdir(parents=True, exist_ok=False)
    binaries = out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    source = Path(__file__).with_name('segment_oracle.c')
    manifest = dict(scope='Resident NF2..8 ordered/unordered indexed segments, EEW32, vstart=0' if indexed else
                    'Resident NF3..8 unit/positive/negative stride segments, vstart=0',
                    cases=[], misaligned_offsets=misaligned,
                    exclusions=['Fault/restart and other segment index EEWs remain separate coverage'])
    manifest['restart_tested']=restart
    if indexed:manifest['index_sew']=index_sew
    if restart:
        manifest.update(scope='Resident aligned '+('NF2..8 indexed EEW32' if indexed else 'NF3..8 unit/positive/negative stride')+' segment restart',
                        restart_points=['one','half_vl','vl_if_representable','last_capacity_element'],
                        exclusions=['Page fault replay, index/source overlap, other index EEWs, misalignment, arbitrary restart points'],
                        trace='28 drained first-segment boundaries per ELF')
    if indexed:
        manifest['scope']=manifest['scope'].replace('EEW32',f'EEW{index_sew}')
        manifest['exclusions'].append('EEW8 capacity capped to power-of-two domain with representable unique offsets')
    for sew, lmul in build.shapes():
        if misaligned and sew==8:continue
        nfs = indexed_fields(sew,lmul,index_sew) if indexed else fields(lmul)
        if not nfs:
            continue
        count = len(nfs)*4
        name = 'rvv_segments'+('_indexed' if indexed else '')+(f'_ei{index_sew}' if indexed and index_sew!=32 else '')+('_misaligned' if misaligned else '')+('_restart' if restart else '')+f'_e{sew}_{lmul}'
        asm = out/(name+'.S')
        asm.write_text(assembly(sew, lmul, indexed, restart,index_sew))
        (out/'operations.h').write_text('\n'.join(
            'extern unsigned long op_%d(const void *,void *,const void *,unsigned long,unsigned long,long,unsigned long);'%i
            for i in range(count)) + '\n#define FUNCTIONS ' +
            ','.join(f'op_{i}' for i in range(count)) +
            '\n#define FIELDS '+','.join(str(nf) for nf in nfs for _ in range(4))+
            f'\n#define OP_COUNT {count}\n')
        binary = binaries/name
        subprocess.run([cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
            '-nostdlib', '-static', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
            '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}',f'-DINDEXED={int(indexed)}',
            f'-DMISALIGNED={int(misaligned)}',
            f'-DRESTART_SEGMENTS={int(restart)}',
            f'-DINDEX_SEW={index_sew}',
            '-I'+str(out), str(source), str(asm), '-o', str(binary)], check=True)
        manifest['cases'].append(dict(name=name, sew=sew, lmul=lmul, fields=nfs,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_SEGMENT_PASS', timeout_seconds=600 if restart else 180))
    manifest['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (source, Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    entries = ['opt', 'opt/ara-tests'] + ['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'],
            input=('\n'.join(entries)+'\n').encode(), stdout=stream,
            cwd=out/'overlay', check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cross', required=True)
    parser.add_argument('--indexed',action='store_true')
    parser.add_argument('--misaligned',action='store_true')
    parser.add_argument('--restart',action='store_true')
    parser.add_argument('--index-sew',type=int,choices=(8,16,32,64),default=32)
    args = parser.parse_args()
    run(args.out, args.cross,args.indexed,args.misaligned,args.restart,args.index_sew)
