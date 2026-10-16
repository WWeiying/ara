"""Merge/move and gather/slide forms with full-XLEN scalar operands."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS=[('vrgather.vv','v8,v16','predicate'),('vrgather.vx','v8,t3','predicate'),
     ('vrgather.vi','v8,0','predicate'),('vrgather.vi','v8,31','predicate'),
     ('vmerge.vvm','v8,v16','selector'),('vmerge.vxm','v8,t3','selector'),
     ('vmerge.vim','v8,-16','selector'),('vmerge.vim','v8,15','selector'),
     ('vmv.v.v','v8','none'),('vmv.v.x','t3','none'),
     ('vmv.v.i','-16','none'),('vmv.v.i','15','none'),
     ('vslideup.vx','v8,t3','predicate'),('vslidedown.vx','v8,t3','predicate'),
     ('vslideup.vi','v8,0','predicate'),('vslideup.vi','v8,31','predicate'),
     ('vslidedown.vi','v8,0','predicate'),('vslidedown.vi','v8,31','predicate'),
     ('vslide1up.vx','v8,t3','predicate'),('vslide1down.vx','v8,t3','predicate'),
     ('vrgatherei16.vv','v8,v16','predicate')]


def operations(sew,lmul):
    # e8,m8 would require index EMUL16, a reserved register group.
    return OPS[:-1] if (sew,lmul)==(8,'m8') else OPS


def assembly(sew,lmul,restart=False):
    lines=['.text','.global capacity','capacity:','li t0,-1',
           f'vsetvli a0,t0,e{sew},{lmul},tu,mu','ret']
    for i,(opcode,args,mask) in enumerate(operations(sew,lmul)):
        index_width=16 if opcode=='vrgatherei16.vv' else sew
        lines += [f'.global op_{i}',f'op_{i}:',
                  f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vle{sew}.v v8,(a0)',f'vle{index_width}.v v16,(a1)',
                  f'vle{sew}.v v24,(a2)','vlm.v v0,(a5)',
                  f'vsetvli t0,a3,e{sew},{lmul},tu,mu','mv t3,a6']
        if restart:lines += ['csrw vstart,a7']
        lines += [
                  opcode+' v24,'+args+(',v0.t' if mask=='predicate' else ',v0' if mask=='selector' else ''),
                  'csrr a0,vstart',f'vsetvli t0,a4,e{sew},{lmul},tu,mu',
                  f'vse{sew}.v v24,(a2)','ret']
    return '\n'.join(lines)+'\n'


def partition_shapes(only=None,operation_ids=None,split_operations=False):
    legal=build.shapes()
    names={f'e{s}_{l}' for s,l in legal}
    if only is not None and (not only or len(set(only))!=len(only) or set(only)-names):
        raise ValueError('Invalid or duplicate permutation shape')
    selected=[(s,l) for s,l in legal if only is None or f'e{s}_{l}' in only]
    if operation_ids is not None and (not operation_ids or
            any(type(i) is not int or i<0 or i>=len(OPS) for i in operation_ids) or
            len(set(operation_ids))!=len(operation_ids)):
        raise ValueError('Invalid or duplicate permutation operation')
    result=[]
    for sew,lmul in selected:
        ids=list(range(len(operations(sew,lmul)))) if operation_ids is None else sorted(operation_ids)
        if any(i>=len(operations(sew,lmul)) for i in ids):
            raise ValueError('Reserved index EMUL16 at e8,m8')
        if split_operations:
            result.extend((sew,lmul,[i]) for i in ids)
        else:
            result.append((sew,lmul,ids))
    return result


def run(out,cross,restart=False,only=None,operation_ids=None,split_operations=False):
    selected=partition_shapes(only,operation_ids,split_operations)
    partitioned=operation_ids is not None or split_operations
    out.mkdir(parents=True,exist_ok=False)
    binaries=out/'overlay/opt/ara-tests';binaries.mkdir(parents=True)
    source=Path(__file__).with_name('permutation_oracle.c')
    manifest=dict(scope='Merge/move, gather vv/vx/vi/ei16, slide vx/vi and slide1; tu/mu, '+('nonzero restart' if restart else 'vstart=0'),
                  cases=[],operations=OPS,restart_tested=restart,
                  operation_partitioned=partitioned,
                  exclusions=['e8,m8 vrgatherei16 requires reserved index EMUL16',
                              'Destination aliases and physical fractional tails remain separate coverage']+
                             ([] if restart else ['Nonzero restart']))
    if restart:
        manifest['restart_points']=['one','half_vl','vl_if_representable','last_capacity_element']
        manifest['trace']='28 drained first-gather boundaries per ELF'
    for sew,lmul,ids in selected:
        ops=operations(sew,lmul)
        suffix='' if not partitioned else '_ops'+'-'.join(str(i) for i in ids)
        name=f'rvv_permute'+('_restart' if restart else '')+f'_e{sew}_{lmul}'+suffix
        directory=out/name;directory.mkdir()
        header='\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);'%i for i in range(len(ops)))
        header+='\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(len(ops)))
        header+='\n#define OP_COUNT %d\n'%len(ops)
        (directory/'operations.h').write_text(header)
        asm=directory/'operations.S';asm.write_text(assembly(sew,lmul,restart));binary=binaries/name
        subprocess.run([cross+'gcc','-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
            '-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DRESTART_PERMUTATIONS={int(restart)}','-I'+str(directory),
            *([] if not partitioned else [f'-DPERMUTE_OP_MASK={sum(1<<i for i in ids)}']),
            str(source),str(asm),'-o',str(binary)],check=True)
        manifest['cases'].append(dict(name=name,sew=sew,lmul=lmul,
            configurations=len(ids)*3*8*7*4*(4 if restart else 1),operations=ops,
            operation_ids=ids,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_PERMUTE_PASS',timeout_seconds=600 if restart else 180))
    manifest['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source,Path(__file__),Path(build.__file__))}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    entries=['opt','opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'],
            input=('\n'.join(entries)+'\n').encode(),stdout=stream,cwd=out/'overlay',check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--cross',required=True)
    parser.add_argument('--restart',action='store_true')
    parser.add_argument('--only',nargs='+')
    parser.add_argument('--operations',nargs='+',type=int,dest='operation_ids')
    parser.add_argument('--split-operations',action='store_true')
    args=parser.parse_args();run(args.out,args.cross,args.restart,args.only,args.operation_ids,args.split_operations)
