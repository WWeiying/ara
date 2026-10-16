"""vf2/vf4/vf8 extension, legal high-end overlap and physical register tails."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build


def cases():
    result = []
    for sew, lmul in build.shapes():
        for factor in (2, 4, 8):
            if sew // factor < 8:
                continue
            index = [x[0] for x in build.LMULS].index(lmul)
            source_index = index - {2: 1, 4: 2, 8: 3}[factor]
            if source_index >= 0:
                source = build.LMULS[source_index][0]
                result.append((sew, lmul, factor, source))
    return result


def register_count(lmul):
    return 1 if lmul.startswith('mf') else int(lmul[1:])


def assembly(sew, lmul, factor, source):
    dest_regs = register_count(lmul)
    source_regs = register_count(source)
    overlap = not source.startswith('mf')
    lines = ['.text', '.global capacity', 'capacity:', 'li t0,-1',
             f'vsetvli a0,t0,e{sew},{lmul},tu,mu', 'ret']
    for op in range(4 if overlap else 2):
        alias = op >= 2
        src = 24 + dest_regs - source_regs if alias else 8
        insn = 'vsext' if op % 2 else 'vzext'
        lines += [f'.global op_{op}', f'op_{op}:',
                  f'vl{dest_regs}re8.v v24,(a1)',
                  f'vsetvli t0,a4,e{sew//factor},{source},tu,mu',
                  f'vle{sew//factor}.v v{src},(a0)', 'vlm.v v0,(a2)',
                  f'vsetvli t0,a3,e{sew},{lmul},tu,mu',
                  f'{insn}.vf{factor} v24,v{src},v0.t', 'csrr a0,vstart',
                  f'vs{dest_regs}r.v v24,(a1)', 'ret']
    return '\n'.join(lines) + '\n'


def run(out, cross, only=None, operations=None):
    selected = [case for case in cases() if only is None or
                f'rvv_extension_e{case[0]}_{case[1]}_vf{case[2]}' in only]
    if not selected or (only is not None and set(only) != {
            f'rvv_extension_e{s}_{l}_vf{f}' for s, l, f, _ in selected}):
        raise ValueError('Unknown or empty extension selection')
    if operations is not None:
        if (not operations or len(set(operations)) != len(operations) or
                any(type(op) is not int or op not in range(4) for op in operations)):
            raise ValueError('Select distinct extension operations 0..3')
        if any(op >= (2 if source.startswith('mf') else 4)
               for _, _, _, source in selected for op in operations):
            raise ValueError('Overlap operations require source EMUL >= 1')
    out.mkdir(parents=True, exist_ok=False)
    binaries = out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    source_file = Path(__file__).with_name('extension_oracle.c')
    manifest = dict(scope='vf2/vf4/vf8, legal overlap, physical tails, vstart=0',
                    cases=[], exclusions=['Overlap requires source EMUL >= 1'])
    for sew, lmul, factor, source in selected:
        overlap = not source.startswith('mf')
        count = 4 if overlap else 2
        name = f'rvv_extension_e{sew}_{lmul}_vf{factor}'
        operation_ids = list(range(count)) if operations is None else list(operations)
        if operations is not None:
            name += '_ops' + '-'.join(str(op) for op in operation_ids)
        asm = out/(name+'.S')
        asm.write_text(assembly(sew, lmul, factor, source))
        (out/'operations.h').write_text('\n'.join(
            'extern unsigned long op_%d(const void *,void *,const void *,unsigned long,unsigned long);'%i
            for i in range(count)) + '\n#define FUNCTIONS ' +
            ','.join(f'op_{i}' for i in range(count))+'\n')
        binary = binaries/name
        subprocess.run([cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
            '-nostdlib', '-static', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
            '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}', f'-DFACTOR={factor}',
            f'-DDEST_REGS={register_count(lmul)}',
            f'-DSOURCE_REGS={register_count(source)}', f'-DOP_COUNT={count}',
            *([] if operations is None else
              [f'-DEXTENSION_OP_MASK={sum(1 << op for op in operation_ids)}']),
            '-I'+str(out), str(source_file), str(asm), '-o', str(binary)], check=True)
        manifest['cases'].append(dict(name=name, sew=sew, lmul=lmul,
            factor=factor, overlap=overlap,
            operation_ids=operation_ids, configurations=84*len(operation_ids),
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            pass_marker='RVV_EXTENSION_PASS', timeout_seconds=180))
    manifest['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (source_file, Path(__file__))}
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
    parser.add_argument('--only', nargs='+')
    parser.add_argument('--operations', nargs='+', type=int)
    args = parser.parse_args()
    run(args.out, args.cross, args.only, args.operations)
