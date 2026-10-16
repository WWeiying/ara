"""Legal low-end narrowing overlap, checking the entire physical source group."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build
import extensions
import widths


def assembly(sew, lmul):
    index = [x[0] for x in build.LMULS].index(lmul)
    double = build.LMULS[index+1][0]
    regs = extensions.register_count(double)
    lines = ['.text', '.global capacity', 'capacity:', 'li t0,-1',
             f'vsetvli a0,t0,e{sew},{lmul},tu,mu', 'ret']
    for i, op in enumerate(('vnsrl.wi', 'vnsra.wi')):
        lines += [f'.global op_{i}', f'op_{i}:', f'vl{regs}re8.v v24,(a1)',
                  f'vsetvli t0,a4,e{sew*2},{double},tu,mu',
                  f'vle{sew*2}.v v24,(a0)', 'vlm.v v0,(a2)',
                  f'vsetvli t0,a3,e{sew},{lmul},tu,mu',
                  f'{op} v24,v24,3,v0.t', 'csrr a0,vstart',
                  f'vs{regs}r.v v24,(a1)', 'ret']
    return '\n'.join(lines)+'\n'


def run(out, cross):
    out.mkdir(parents=True, exist_ok=False)
    binaries = out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    source = Path(__file__).with_name('extension_oracle.c')
    (out/'operations.h').write_text('\n'.join(
        'extern unsigned long op_%d(const void *,void *,const void *,unsigned long,unsigned long);'%i
        for i in range(2))+'\n#define FUNCTIONS op_0,op_1\n')
    manifest = dict(scope='Low-end overlapping vnsrl/vnsra immediate, physical tails, vstart=0',
                    cases=[], operations=['vnsrl.wi', 'vnsra.wi'])
    for sew, lmul in widths.shapes():
        double = build.LMULS[[x[0] for x in build.LMULS].index(lmul)+1][0]
        name = f'rvv_narrow_alias_e{sew}_{lmul}'
        asm = out/(name+'.S')
        asm.write_text(assembly(sew, lmul))
        binary = binaries/name
        subprocess.run([cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
            '-nostdlib', '-static', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
            '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}', '-DNARROW_SUITE=1',
            f'-DDEST_REGS={extensions.register_count(double)}', '-DOP_COUNT=2',
            '-I'+str(out), str(source), str(asm), '-o', str(binary)], check=True)
        manifest['cases'].append(dict(name=name, sew=sew, lmul=lmul,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_NARROW_ALIAS_PASS', timeout_seconds=180))
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
    args = parser.parse_args()
    run(args.out, args.cross)
