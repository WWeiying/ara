#!/usr/bin/env python3
"""Freeze and run the standalone production multiplier product-port VCS gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
LOCAL = ('product_tb.sv', 'run_product.py', 'test_run_product.py')
PACKAGES = (
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/include/ara_pkg.sv')
MULTIPLIERS = ('hardware/src/lane/simd_mul.sv', 'hardware/src/lane/simd_mul_shared.sv')
DEPENDENCIES = ('hardware/src/lane/simd_mul_shared_product.sv',
                'hardware/src/lane/simd_mul_partition_add.sv')
HEADERS = ('hardware/deps/common_cells/include/common_cells/registers.svh',)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for name, digest in pins.items():
        if sha(name) != digest:
            raise ValueError('Source/image drift: ' + name)


def reference_copy(original, name):
    declaration = rb'\bmodule ' + name.encode() + rb'\b'
    if len(re.findall(declaration, original)) != 1 or b'output logic [127:0] product_o' in original:
        raise ValueError('Reference must precede the new product port')
    # Rename the declaration and optional named endmodule together.
    return re.sub(rb'\b' + name.encode() + rb'\b', name.encode() + b'_before', original)


def check_log(text):
    if re.search(r'(?im)(?:fatal|error|assertion failed|timeout)', text):
        raise ValueError('Simulator failure in log')
    marker = 'STAGE2_PRODUCT_PASS configurations=24 shared_no_bypass=3'
    if text.count(marker) != 1:
        raise ValueError('Missing/duplicate product completion')
    pattern = (r'^PRODUCT_CASE id=(\d+) shared=(\d+) sew=(\d+) pipes=(\d+) bypass=(\d+) '
               r'accepted=(\d+) retired=(\d+) flushed=(\d+) checks=(\d+) stalled=(\d+)$')
    rows = [tuple(map(int, m)) for m in re.findall(pattern, text, re.M)]
    if len(rows) != 27 or {r[0] for r in rows} != set(range(27)):
        raise ValueError('Missing/duplicate configuration')
    for identity, shared, sew, pipes, bypass, accepted, retired, flushed, checks, stalled in rows:
        expected = (identity // 12, 8 << ((identity % 12) // 3), identity % 3, 1) if identity < 24 else (1, 8, identity - 24, 0)
        if (shared, sew, pipes, bypass) != expected:
            raise ValueError('Wrong configuration geometry')
        minimum = 199168 if sew == 8 else 2560
        if accepted != retired + flushed or retired < minimum or checks < retired or stalled == 0:
            raise ValueError('Insufficient checks or broken accounting')
        if pipes > 0 and (not shared or not bypass or sew != 8) and flushed == 0:
            raise ValueError('Missing pending reset coverage')
    return dict(configurations=24, shared_no_bypass=3,
                accepted=sum(r[5] for r in rows), retired=sum(r[6] for r in rows),
                flushed=sum(r[7] for r in rows), checks=sum(r[8] for r in rows))


def prepare(out):
    if out.parent != OUT:
        raise ValueError('Use a unique direct signoff out child')
    branch = subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip()
    if branch != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong signoff worktree')
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('Host VCS not found')
    out.mkdir(exist_ok=False)
    inputs = out / 'inputs'
    pins = {}
    for rel in (*PACKAGES, *MULTIPLIERS, *DEPENDENCIES, *HEADERS, *(str(HERE.relative_to(ROOT) / n) for n in LOCAL)):
        source, destination = ROOT / rel, inputs / rel
        expected = sha(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha(destination) != expected:
            raise ValueError('Copy race: ' + rel)
        pins[str(source)] = pins[str(destination)] = expected
    local = inputs / HERE.relative_to(ROOT)
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    refs = []
    reference_identity = {}
    for rel in MULTIPLIERS:
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', revision + ':' + rel])
        name = Path(rel).stem
        renamed = reference_copy(original, name)
        reference = inputs / (name + '_before.sv')
        reference.write_bytes(renamed)
        pins[str(reference)] = sha(reference)
        refs.append(reference)
        reference_identity[rel] = dict(commit=revision, sha256=hashlib.sha256(original).hexdigest())
    save(out / 'reference-identity.json', reference_identity)
    filelist = inputs / 'sources.f'
    filelist.write_text('+incdir+' + str(inputs / 'hardware/deps/common_cells/include') + '\n' +
        '\n'.join(str(inputs / p) for p in (*PACKAGES, *MULTIPLIERS, *DEPENDENCIES)) + '\n' +
        '\n'.join(map(str, refs)) + '\n' + str(local / 'product_tb.sv') + '\n')
    config = dict(vcs=vcs, local=str(local), timeout_seconds=1200,
                  source_scope='two multipliers, exact arithmetic/package/include dependencies; no lane/vmfpu inventory')
    save(out / 'selection.json', config)
    for p in (filelist, out / 'reference-identity.json', out / 'selection.json', Path(vcs).resolve()):
        pins[str(p)] = sha(p)
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', configurations=24, extra_no_bypass=3,
                                    frozen_runner=str(local / 'run_product.py')))
    print(local / 'run_product.py')


def command(argv, cwd, log, deadline):
    with log.open('w') as stream:
        subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                       timeout=max(1, deadline - time.monotonic()), check=True)


def execute(out):
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_product.py':
        raise ValueError('Execute only the frozen runner')
    pins = json.loads((out / 'source-pins.json').read_text())
    work = out / 'work'
    work.mkdir(exist_ok=False)
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', scope='standalone multiplier products and legacy interface; not VMFPU/SoC acceptance')
    try:
        verify(pins)
        command([sys.executable, '-B', str(Path(config['local']) / 'test_run_product.py')],
                work, work / 'host-tests.log', deadline)
        compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                       '-top', 'stage2_product_tb', '-o', 'simv', '-f', str(out / 'inputs/sources.f')]
        run_cmd = [str(work / 'simv'), '-no_save']
        save(work / 'commands.json', dict(compile=compile_cmd, run=run_cmd))
        print('STAGE2_PRODUCT_COMPILING', flush=True)
        command(compile_cmd, work, work / 'compile.log', deadline)
        verify(pins)
        image = {str(p): sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
        image[str(work / 'simv')] = sha(work / 'simv')
        save(work / 'image-pins.json', image)
        print('STAGE2_PRODUCT_RUNNING', flush=True)
        command(run_cmd, work, work / 'run.log', deadline)
        report['work'] = check_log((work / 'run.log').read_text())
        verify(pins)
        verify(image)
        save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', post_pins_match=True, post_image_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): sha(p) for p in work.glob('*') if p.is_file()}
    save(out / 'report.json', report)
    print('STAGE2_PRODUCT_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.execute:
        return execute(out)
    prepare(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
