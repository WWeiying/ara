#!/usr/bin/env python3
"""Freeze three new controls; reuse the comparison builder, no RTL or VCS."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
COMPARISON = HERE.parent / 'comparison'
sys.path.insert(0, str(COMPARISON))
from prepare_build import build, save, sha, INTEGRATION


def main():
    out = HERE / 'prepared01'
    out.mkdir(exist_ok=False)
    dependencies = [COMPARISON / n for n in ('prepare_build.py', 'matrix.c', 'capture.S', 'reference.py')]
    dependencies += [INTEGRATION / n for n in ('prepare.py', 'run.py', 'startup.S', 'runtime.c', 'replay.ld')]
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(INTEGRATION / name, out / name)
    shutil.copyfile(COMPARISON / 'capture.S', out / 'capture.S')
    records = []
    for name, start, scalar in [('vv_restart16', 16, 0), ('vv_start0', 0, 0), ('vf_restart16', 16, 1)]:
        directory = out / name
        (directory / 'original').mkdir(parents=True)
        shutil.copyfile(HERE / 'control.c', directory / 'case.c')
        asm = (HERE / 'compare.S').read_text()
        if scalar:
            asm = asm.replace('vmfeq.vv v24,v8,v16,v0.t', 'vmfeq.vf v24,v8,ft0,v0.t')
        (directory / 'original/scenario.S').write_text(asm)
        records.append(dict(id=name, sew=16, control=0,
            defines=[f'SOURCE_MAIN={name}_main', f'START={start}', f'SCALAR={scalar}'],
            pass_marker=f'FP_SOURCE_PASS {name} cases=1 errors=0 flags=1 start_after=0',
            scope='NEW directed finite-value control, not historical original',
            vl=32, vstart=start, lmul='m1', source_elements=64,
            truth='0x9e35c692396d58b3', active_mask='0xd6ad',
            expected_fflags=1, expected_frm=1, expected_vcsr=5))
    provenance = dict(schema_version=1, vlen=1024, nr_lanes=4, cases=records,
        scope='3 new independent FP source-origin controls; directory original is builder API only, NOT archived source',
        dependencies={str(p): sha(p) for p in dependencies},
        source_pins={str(p): sha(p) for p in (HERE/'control.c', HERE/'compare.S', Path(__file__))})
    provenance['files'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'provenance.json', provenance)
    host = HERE / 'host01'
    host.mkdir(exist_ok=False)
    command = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DHOST_CHECK', str(HERE/'control.c'), '-o', str(host/'check')]
    subprocess.run(command, check=True)
    result = subprocess.run([str(host/'check')], text=True, capture_output=True)
    save(host/'result.json', dict(command=command, returncode=result.returncode, stdout=result.stdout,
        stderr=result.stderr, source_sha256=sha(HERE/'control.c')))
    if result.returncode:
        raise RuntimeError('host oracle negatives failed: '+str(result.returncode))
    print(result.stdout.strip())
    build(out, provenance, True, HERE/'spike01')
    build(out, provenance, False, HERE/'soc01')


if __name__ == '__main__':
    main()
