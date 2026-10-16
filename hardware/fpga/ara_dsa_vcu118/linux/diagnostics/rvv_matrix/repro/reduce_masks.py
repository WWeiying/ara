"""Reduce measured mask-prefix failures without replacing their oracle or assembly."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from trace_masks import sha


def fields(output, marker):
    lines = [line for line in output.splitlines() if line.startswith(marker + ' ')]
    if len(lines) != 1:
        raise ValueError('Expected one ' + marker)
    pairs = [token.split('=') for token in lines[0].split()[1:]]
    result = {key: int(value) for key, value in pairs}
    if len(result) != len(pairs):
        raise ValueError('Duplicate field')
    return result, lines[0]


def stimulus(result):
    if result['status'] != 'failed' or result['exit_code'] != 1:
        raise ValueError('Not a completed architectural failure')
    first, _ = fields(result['output'], 'RVV_MASK_FIRST')
    bit, detail = fields(result['output'], 'RVV_MASK_BIT')
    for key in ('seed', 'op', 'vl', 'mask', 'vstart'):
        if first[key] != bit[key] or first[key] < 0:
            raise ValueError('Inconsistent stimulus')
    if bit['expected'] == bit['actual'] or first['errors'] <= 0:
        raise ValueError('Missing wrong bit')
    return first, detail


def reduce(source, measured):
    replacements = {
        'unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};':
            'unsigned lengths[]={%d};' % measured['vl'],
        'for(unsigned seed=0;seed<3;++seed)':
            'for(unsigned seed=%d;seed<%d;++seed)' % (measured['seed'], measured['seed'] + 1),
        'for(unsigned raw_op=0;raw_op<OP_COUNT;++raw_op)':
            'for(unsigned raw_op=%d;raw_op<%d;++raw_op)' % (measured['op'], measured['op'] + 1),
        'for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)':
            'for(unsigned l=0;l<1;++l)for(unsigned mode=%d;mode<%d;++mode)' %
            (measured['mask'], measured['mask'] + 1),
        'trial<(RESTART_MASKS ? 4U:1U)': 'trial<1U',
        '            for(unsigned i=0;i<128;++i)predicate[i]=':
            '            start=%d;\n            for(unsigned i=0;i<128;++i)predicate[i]=' % measured['vstart'],
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('Source contract changed: ' + old)
        source = source.replace(old, new)
    return source


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--cross', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.trace / 'manifest.json').read_text())
    report_bytes = a.report.read_bytes()
    raw = json.loads(report_bytes)
    report = raw.get('report', raw)
    inputs = {c['name']: c for c in report['inputs']['cases']}
    results = {r['name']: r for r in report['results']}
    a.out.mkdir(exist_ok=False)
    binaries = a.out / 'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    output = dict(scope='Single measured mask stimulus; equivalence requires board retest',
                  board_reproduction_confirmed=False, cases=[],
                  trace_manifest_sha256=sha(a.trace / 'manifest.json'),
                  trace_report_sha256=hashlib.sha256(report_bytes).hexdigest(), reducer_sha256=sha(Path(__file__)))
    (a.out / 'prefix_board_report.json').write_bytes(report_bytes)
    for case in manifest['cases']:
        parent = case['name']
        if inputs[parent]['sha256'] != case['sha256']:
            raise ValueError('Deployed trace ELF changed')
        source_dir = a.trace / parent
        for filename, expected in case['scenario_sources'].items():
            if sha(source_dir / filename) != expected:
                raise ValueError('Trace source changed')
        if sha(source_dir / 'original_rebuilt.elf') != case['original_elf_sha256']:
            raise ValueError('Original ELF rebuild mismatch')
        measured, detail = stimulus(results[parent])
        name = parent.replace('rvv_trace_', 'rvv_small_', 1)
        d = a.out / name
        d.mkdir()
        for filename in ('scenario.S', 'operations.h'):
            shutil.copy2(source_dir / filename, d / filename)
        (d / 'scenario.c').write_text(reduce((source_dir / 'scenario.c').read_text(), measured))
        scalar = 'scalar_restart' in parent
        flags = [a.cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static',
                 '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
                 '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
                 '-Wall', '-Wextra', '-Werror', f'-DSEW={case["sew"]}',
                 f'-DSCALAR_FORMS={int(scalar)}', '-DALIASES=0',
                 f'-DCOMPARISON_ALIASES={int(not scalar)}', '-DCARRY_FORMS=0', '-DRESTART_MASKS=1',
                 '-I'+str(d)]
        binary = binaries / name
        subprocess.run(flags + [str(d/'scenario.c'), str(d/'scenario.S'), '-o', str(binary)], check=True)
        output['cases'].append(dict(case, name=name, sha256=sha(binary),
            scenario_role='single_stimulus', prefix_name=parent, prefix_elf_sha256=case['sha256'],
            measured_stimulus=measured, prefix_failure_detail=detail,
            scenario_sources={f:sha(d/f) for f in ('scenario.c', 'scenario.S', 'operations.h')}))
    (a.out/'manifest.json').write_text(json.dumps(output, indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'], cwd=a.out/'overlay',
            input=('opt\nopt/ara-tests\n'+''.join('opt/ara-tests/'+c['name']+'\n' for c in output['cases'])).encode(),
            stdout=stream, check=True)
    print('CASES', len(output['cases']))


if __name__ == '__main__':
    main()
