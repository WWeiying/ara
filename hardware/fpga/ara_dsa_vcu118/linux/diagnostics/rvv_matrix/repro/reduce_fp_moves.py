"""Extract one measured FP-move stimulus per failing ELF, without changing its oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import fp_moves
import floating


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def single_trial(source, fields):
    first = source.index('    for(unsigned seed=0;')
    last = source.index('        uint64_t scalar_bits=', first)
    required = ('seed', 'scalar', 'invalid_box', 'op', 'vl', 'mask', 'sticky', 'vstart')
    if any(k not in fields or not isinstance(fields[k], int) or fields[k] < 0 for k in required):
        raise ValueError('Incomplete measured stimulus')
    declarations = dict(seed=fields['seed'], scalar=fields['scalar'], invalid=fields['invalid_box'],
                        op=fields['op'], vl=fields['vl'], mode=fields['mask'],
                        sticky=fields['sticky'], start=fields['vstart'])
    block = '    {\n' + ''.join(f'        unsigned {k}={v};\n' for k, v in declarations.items())
    block += '        unsigned prior=errors;\n'
    result = source[:first] + block + source[last:]
    result = result.replace('    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};\n', '')
    result = result.replace('        uint64_t scalar_bits=',
        '        text("RVV_REDUCED_BEGIN cases=1\\n");\n        uint64_t scalar_bits=', 1)
    return result


def prefix_trials(source, fields):
    # Retain the original loop order and stop after the measured first failing tuple.
    single_trial(source, fields)
    variables = dict(seed=fields['seed'], scalar=fields['scalar'], invalid=fields['invalid_box'],
                     op=fields['op'], vl=fields['vl'], mode=fields['mask'],
                     sticky=fields['sticky'], start=fields['vstart'])
    condition = ' && '.join(f'{k}=={v}' for k, v in variables.items())
    assert source.count('        ++cases;') == 1
    source = source.replace('        ++cases;',
        '        ++cases;\n        if('+condition+')goto selected_done;')
    marker = '    text(errors ? "RVV_FP_MOVE_FAIL sew="'
    assert source.count(marker) == 1
    return source.replace(marker, 'selected_done:\n'+marker)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--report', type=Path, required=True)
    cli.add_argument('--original-build', type=Path, required=True)
    cli.add_argument('--cross', required=True)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--prefix', action='store_true',
                     help='Preserve original preceding trials up to the measured failure tuple')
    args = cli.parse_args()
    report_bytes = args.report.read_bytes()
    report = json.loads(report_bytes)
    source = TOOLS/'fp_move_oracle.c'
    selected = []
    for result in report['results']:
        match = re.fullmatch(r'rvv_fp_move_restart_e(16|32|64)_(m[f1248]+)_ops([0-7])', result['name'])
        if result['status'] != 'failed' or not match:
            continue
        sew, lmul, operation = int(match[1]), match[2], int(match[3])
        original = json.loads((args.original_build/f'op{operation}'/'manifest.json').read_text())
        for path in (source, Path(fp_moves.__file__), Path(floating.__file__)):
            if sha(path) != original['source_sha256'][path.name]:
                raise ValueError('Original generator/oracle source changed: '+str(path))
        original_case, = [c for c in original['cases'] if c['name'] == result['name']]
        board_case, = [c for c in report['inputs']['cases'] if c['name'] == result['name']]
        assert original_case['sha256'] == board_case['sha256']
        line = next(x for x in result['output'].splitlines() if x.startswith('RVV_FP_MOVE_DETAIL '))
        fields = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
        assert fields['op'] == operation and fields['errors'] > 0
        selected.append((result, sew, lmul, operation, fields, line, original_case))
    if not selected:
        raise ValueError('No measured failing FP move cases')
    args.out.mkdir(parents=True, exist_ok=False)
    binaries = args.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    (args.out/'original_board_report.json').write_bytes(report_bytes)
    manifest = dict(scope='Single measured stimulus per original failing FP-move ELF',
        original_report_sha256=hashlib.sha256(report_bytes).hexdigest(), cases=[],
        source_sha256={p.name: sha(p) for p in (source, Path(fp_moves.__file__),
                        Path(floating.__file__), Path(__file__))},
        board_reproduction_confirmed=False, original_preceding_trials_removed=not args.prefix)
    for result, sew, lmul, operation, fields, detail, parent in selected:
        name = result['name'].replace('rvv_fp_', 'rvv_prefix_fp_' if args.prefix else 'rvv_small_fp_', 1)
        directory = args.out/name
        directory.mkdir()
        c = directory/'scenario.c'
        c.write_text((prefix_trials if args.prefix else single_trial)(source.read_text(), fields))
        asm = directory/'scenario.S'
        asm.write_text(fp_moves.assembly(sew, lmul, True))
        (directory/'inputs.h').write_text('static const word inputs[16]={'+
            ','.join('UINT64_C(0x%x)' % x for x in floating.BITS[sew])+'};\n')
        (directory/'operations.h').write_text('\n'.join(
            'extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,void *);'%i
            for i in range(8))+'\n#define FUNCTIONS '+','.join(f'op_{i}' for i in range(8))+'\n')
        binary = binaries/name
        subprocess.run([args.cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
            '-nostdlib', '-static', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
            '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
            '-Wl,--build-id=none', '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}',
            f'-DMOVE_OP_MASK={1 << operation}',
            '-DRESTART_MOVES=1', '-DDETAIL_MOVES=1', '-I'+str(directory), str(c), str(asm),
            '-o', str(binary)], check=True)
        with (directory/'scenario.dis').open('w') as output:
            subprocess.run([args.cross+'objdump', '-d', str(binary)], stdout=output, check=True)
        manifest['cases'].append(dict(name=name, sew=sew, lmul=lmul, operation_ids=[operation],
            sha256=sha(binary), pass_marker='RVV_FP_MOVE_PASS', timeout_seconds=30,
            scenario_role='original_prefix_with_data_detail' if args.prefix else 'single_stimulus',
            **({} if args.prefix else dict(configurations=1)),
            original_name=parent['name'], original_elf_sha256=parent['sha256'],
            measured_stimulus=fields, original_failure_detail=detail,
            scenario_sources={p.name: sha(p) for p in (c, asm, directory/'inputs.h', directory/'operations.h')}))
    (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    entries=['opt', 'opt/ara-tests']+['opt/ara-tests/'+c['name'] for c in manifest['cases']]
    with (args.out/'overlay.cpio').open('wb') as output:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'], cwd=args.out/'overlay',
            input=('\n'.join(entries)+'\n').encode(), stdout=output, check=True)
    print(json.dumps(dict(cases=len(selected), output=str(args.out))))


if __name__ == '__main__':
    main()
