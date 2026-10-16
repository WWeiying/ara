"""Integer scalar forms with an independent scalar oracle and bounded shapes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import build

OPS = [(op.replace('.vv', '.vx'), 'v8, t3') for op, _ in build.OPS[:17]] + [
    (op, 'v8, t3') for op in ('vrsub.vx', 'vmulhu.vx', 'vmulh.vx', 'vmulhsu.vx')]
MACC_OPS = [(op+'.'+form, 'v8, v16' if form=='vv' else 't3, v8')
            for form in ('vv','vx') for op in ('vmacc','vnmsac','vmadd','vnmsub')]
IMMEDIATE_SPECS = [(op, code, imm) for op,code in
                   (('vadd',0),('vrsub',17),('vand',2),('vor',3),('vxor',4),
                    ('vsll',5),('vsrl',6),('vsra',7))
                   for imm in ((0,31) if op.startswith('vs') else (-16,15))]
IMMEDIATE_OPS = [(op+'.vi',f'v8, {imm}') for op,_,imm in IMMEDIATE_SPECS]
CARRY_OPS = [('vadc.vvm','v8, v16'),('vadc.vxm','v8, t3'),
             ('vadc.vim','v8, -16'),('vadc.vim','v8, 15'),
             ('vsbc.vvm','v8, v16'),('vsbc.vxm','v8, t3')]


def macc_operations(alias_source=None):
    if alias_source is None:
        return MACC_OPS
    if alias_source not in ('first', 'second', 'both'):
        raise ValueError('Unknown source alias')
    # vx has only one explicit vector source; second/both are vv-only.
    return [(op, args.replace('v8', 'v24') if alias_source == 'first'
             else args.replace('v16', 'v24') if alias_source == 'second'
             else args.replace('v8', 'v24').replace('v16', 'v24'))
            for op, args in MACC_OPS if alias_source == 'first' or op.endswith('.vv')]


def assembly(sew, lmul, operations, unmasked=False, chain_steps=1, mixed_chain=False):
    if chain_steps not in range(1, 9):
        raise ValueError('Chain length must be 1..8')
    if mixed_chain and chain_steps == 1:
        raise ValueError('Mixed chain requires multiple instructions')
    if chain_steps > 1 and any(op not in {x[0] for x in MACC_OPS} for op,_ in operations):
        raise ValueError('Chains require multiply-add operations')
    carry=operations==CARRY_OPS
    if carry and unmasked:
        raise ValueError('Data carry/borrow vm=1 encodings are reserved')
    result=build.assembly(sew,lmul,operations=operations,scalar_from_input=True)
    if chain_steps > 1:
        replacements={}
        for i,(op,args) in enumerate(operations):
            original=f'{op} v24, {args}, v0.t'
            sequence=[MACC_OPS[(i & ~3)+((i+step)%4)][0] if mixed_chain else op
                      for step in range(chain_steps)]
            replacements[original]=[f'{name} v24, {args}, v0.t' for name in sequence]
        result='\n'.join(expanded for line in result.splitlines()
                         for expanded in replacements.get(line,[line]))+'\n'
    if carry:
        return result.replace(', v0.t',', v0')
    return result.replace(', v0.t','') if unmasked else result


def run(out, cross, multiply_add=False, immediate=False, unmasked=False, carry=False, accumulators=False, alias_source=None, restart=False, chain_steps=1, mixed_chain=False):
    if chain_steps not in range(1, 9):
        raise ValueError('Chain length must be 1..8')
    if mixed_chain and chain_steps == 1:
        raise ValueError('Mixed chain requires multiple instructions')
    if chain_steps > 1 and (not multiply_add or restart):
        raise ValueError('Chain supplement requires multiply-add with vstart=0')
    if restart and not multiply_add:
        raise ValueError('This restart supplement requires multiply-add')
    if alias_source not in (None, 'first', 'second', 'both'):
        raise ValueError('Unknown source alias')
    if alias_source and not multiply_add:
        raise ValueError('Source aliases require multiply-add')
    if accumulators and not multiply_add:
        raise ValueError('Accumulator patterns require multiply-add')
    if sum((multiply_add,immediate,carry))>1:
        raise ValueError('Select one integer family')
    if carry and unmasked:
        raise ValueError('Data carry/borrow vm=1 encodings are reserved')
    out.mkdir(parents=True, exist_ok=False)
    binaries = out / 'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    source = Path(__file__).with_name('oracle.c')
    ops = CARRY_OPS if carry else MACC_OPS if multiply_add else IMMEDIATE_OPS if immediate else OPS
    if alias_source:
        ops = macc_operations(alias_source)
    seeds = 3 if immediate else 5
    header = '\n'.join(
        'extern unsigned long op_%d(const word *,const word *,word *,unsigned long,'
        'unsigned long,const uint8_t *,unsigned long,unsigned long);' % i
        for i in range(len(ops)))
    header += '\n#define OPERATION_COUNT %d\n' % len(ops)
    header += '#define OPERATION_FUNCTIONS ' + ','.join(f'op_{i}' for i in range(len(ops))) + '\n'
    header += '#define OPERATION_NAMES ' + ','.join(json.dumps(op) for op, _ in ops) + '\n'
    header += '#define OPERATION_KINDS ' + ','.join('4' for _ in ops) + '\n'
    header += '#define INTEGER_EXTENSION 0\n#define AGNOSTIC_POLICY 0\n'
    header += '#define INTEGER_SCALAR_SUITE 1\n#define INPUT_SEEDS %d\n' % seeds
    header += '#define UNMASKED_SUITE %d\n' % unmasked
    if restart:
        header += '#define RESTART_SUITE 1\n#define TRACE_RESTART_BOUNDARIES 1\n'
    if carry:
        header += '#define INTEGER_CARRY_SUITE 1\n#define CARRY_INPUT_SUITE 1\n'
    if multiply_add:
        header += '#define INTEGER_MACC_SUITE 1\n'
    if chain_steps > 1:
        header += '#define MACC_CHAIN_STEPS %d\n#define MACC_CHAIN_MIXED %d\n' % (chain_steps,mixed_chain)
    if alias_source:
        header += '#define MACC_ALIAS_FIRST %d\n#define MACC_ALIAS_SECOND %d\n' % (
            alias_source in ('first', 'both'), alias_source in ('second', 'both'))
    if accumulators:
        header += '#define MACC_ACCUMULATORS 1\n#define ACCUMULATOR_TRIALS 5\n'
    if immediate:
        header += '#define INTEGER_IMMEDIATE_SUITE 1\n'
        header += '#define IMMEDIATE_ORACLE '+','.join(str(x[1]) for x in IMMEDIATE_SPECS)+'\n'
        header += '#define IMMEDIATE_VALUES '+','.join(str(x[2]) for x in IMMEDIATE_SPECS)+'\n'
    (out / 'operations.h').write_text(header)
    family = 'carry' if carry else 'macc' if multiply_add else 'immediate' if immediate else 'scalar'
    if accumulators:
        family += '_accumulators'
    if alias_source:
        family += '_alias_' + alias_source
    if unmasked:
        family += '_unmasked'
    if restart:
        family += '_restart'
    if chain_steps > 1:
        family += ('_mixed_chain' if mixed_chain else '_repeat_chain') + str(chain_steps)
    manifest = dict(scope=('Integer '+family+' forms')+
                    '; input seeds/boundaries, seven VLs, four predicates; '+
                    ('four representable vstart boundaries' if restart else 'vstart=0'),
                    cases=[], operations=[op for op, _ in ops], restart_tested=restart,
                    restart_boundaries=['one','half_vl','vl_if_representable_else_cap_minus_one','cap_minus_one'] if restart else [],
                    trace_boundary_lines_per_elf=28 if restart else 0,
                    input_seeds=seeds, unmasked=unmasked,
                    source_alias=alias_source,
                    chain_steps=chain_steps, mixed_chain=mixed_chain,
                    chain_intermediate_readback=False,
                    mask_semantics='carry/borrow input' if carry else 'ignored' if unmasked else 'execution predicate',
                    immediate_specs=IMMEDIATE_SPECS if immediate else [],
                    accumulator_patterns=['zero','all_ones','sign_bit','alternating_bits','per_element'] if accumulators else ['sentinel_0x5b'],
                    configurations_per_elf=len(ops)*seeds*7*4*(5 if accumulators else 1)*(4 if restart else 1))
    for sew, lmul in build.shapes():
        name = f'rvv_integer_{family}_e{sew}_{lmul}'
        asm = out / (name + '.S')
        asm.write_text(assembly(sew,lmul,ops,unmasked,chain_steps,mixed_chain))
        binary = binaries / name
        subprocess.run([cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
                        '-nostdlib', '-static', '-ffreestanding', '-fno-builtin',
                        '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                        '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
                        '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}', '-I'+str(out),
                        str(source), str(asm), '-lgcc', '-o', str(binary)], check=True)
        manifest['cases'].append(dict(name=name, sew=sew, lmul=lmul,
                                     sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                                     pass_marker='RVV_MATRIX_PASS', timeout_seconds=180))
    manifest['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (source, Path(__file__), Path(build.__file__))}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    entries = ['opt', 'opt/ara-tests'] + ['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (out / 'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'],
                       input=('\n'.join(entries)+'\n').encode(), stdout=stream,
                       cwd=out / 'overlay', check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cross', required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--multiply-add', action='store_true')
    group.add_argument('--immediate', action='store_true')
    group.add_argument('--carry-borrow', action='store_true')
    parser.add_argument('--unmasked', action='store_true')
    parser.add_argument('--accumulators', action='store_true')
    parser.add_argument('--alias-source', choices=('first', 'second', 'both'))
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--chain-steps', type=int, default=1)
    parser.add_argument('--mixed-chain', action='store_true')
    args = parser.parse_args()
    run(args.out, args.cross, args.multiply_add, args.immediate, args.unmasked,args.carry_borrow,args.accumulators,args.alias_source,args.restart,args.chain_steps,args.mixed_chain)
