"""Retain the exact original widening-reduction first trial (VL=0)."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from trace_masks import sha, TOOLS


def reduce(source):
    for old, new in (
        ('unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};', 'unsigned lengths[]={0};'),
        ('seed<3', 'seed<1'), ('op<OP_COUNT', 'op<1'),
        ('rm<(FLOAT_REDUCTION ? 5u:1u)', 'rm<1'), ('l<7', 'l<1'), ('mode<4', 'mode<1')):
        if source.count(old) != 1:
            raise ValueError('Source contract changed: '+old)
        source = source.replace(old, new)
    return source


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--cross', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    original = json.loads((a.original/'manifest.json').read_text())
    parent = 'rvv_reduction_fpwide_e32_m8'
    case, = [c for c in original['cases'] if c['name'] == parent]
    report = json.loads(a.report.read_text())
    deployed, = [c for c in report['inputs']['cases'] if c['name'] == parent]
    result, = [r for r in report['results'] if r['name'] == parent]
    if case['sha256'] != deployed['sha256'] or result['exit_code'] != 132:
        raise ValueError('Original failed ELF evidence differs')
    source = TOOLS/'reduction_oracle.c'
    if sha(source) != original['source_sha256']['reduction_oracle.c']:
        raise ValueError('Original oracle changed')
    a.out.mkdir(exist_ok=False)
    name = 'rvv_small_fpwide_original_vl0'
    d = a.out/name
    d.mkdir()
    shutil.copy2(a.original/(parent+'.S'), d/'scenario.S')
    shutil.copy2(a.original/'operations.h', d/'operations.h')
    flags = [a.cross+'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
             '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
             '-Wall', '-Wextra', '-Werror', '-DSEW=32', '-DDEST_SEW=64', '-DFLOAT_REDUCTION=1',
             '-DOP_COUNT=2', '-I'+str(d)]
    rebuilt = d/'original_rebuilt.elf'
    subprocess.run(flags+[str(source), str(d/'scenario.S'), '-lgcc', '-o', str(rebuilt)], check=True)
    if sha(rebuilt) != case['sha256']:
        raise ValueError('Original ELF rebuild not byte-identical')
    (d/'scenario.c').write_text(reduce(source.read_text()))
    binaries = a.out/'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    binary = binaries/name
    subprocess.run(flags+[str(d/'scenario.c'), str(d/'scenario.S'), '-lgcc', '-o', str(binary)], check=True)
    with (d/'scenario.dis').open('w') as stream:
        subprocess.run([a.cross+'objdump', '-d', str(binary)], stdout=stream, check=True)
    reduced = dict(case, name=name, sha256=sha(binary), timeout_seconds=30,
                   original_name=parent, original_elf_sha256=case['sha256'],
                   original_rebuild_byte_identical=True, scenario_role='single_stimulus',
                   measured_stimulus=dict(seed=0, op=0, rm=0, vl=0, mask=0),
                   scenario_sources={f:sha(d/f) for f in ('scenario.c','scenario.S','operations.h')})
    manifest = dict(scope='Original first widening-reduction trial; board equivalence pending',
                    cases=[reduced], board_reproduction_confirmed=False,
                    original_manifest_sha256=sha(a.original/'manifest.json'),
                    original_report_sha256=sha(a.report), reducer_sha256=sha(Path(__file__)))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with (a.out/'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio','-o','-H','newc','--owner=0:0'], cwd=a.out/'overlay',
                       input=('opt\nopt/ara-tests\nopt/ara-tests/'+name+'\n').encode(),
                       stdout=stream,check=True)
    print('BYTE_IDENTICAL_ORIGINAL; SINGLE_VL0_BUILT')


if __name__ == '__main__':
    main()
