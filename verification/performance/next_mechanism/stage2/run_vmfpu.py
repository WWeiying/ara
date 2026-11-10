#!/usr/bin/env python3
"""Freeze and run the real VMFPU integer borrowing gate with host VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
SOURCES = (
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/include/ariane_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/include/rvv_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/spill_register_flushable.sv',
    'hardware/deps/common_cells/src/spill_register.sv',
    'hardware/deps/tech_cells_generic/src/rtl/tc_clk.sv',
    'hardware/deps/cva6/core/serdiv.sv',
    'hardware/src/lane/simd_div.sv',
    'hardware/src/lane/power_gating_generic.sv',
    'hardware/src/lane/simd_mul.sv',
    'hardware/src/lane/simd_mul_shared_product.sv',
    'hardware/src/lane/simd_mul_partition_add.sv',
    'hardware/src/lane/simd_mul_shared.sv',
    'hardware/src/lane/qbs_lane_mul_borrow.sv',
    'hardware/src/lane/vmfpu.sv',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def verify(pins):
    for name, expected in pins.items():
        if sha(name) != expected:
            raise ValueError('Pinned source/image drift: ' + name)


def prepare(out):
    if out.parent != OUT or not shutil.which('vcs'):
        raise ValueError('Require unique signoff output and host VCS')
    for rel in SOURCES:
        if not (ROOT / rel).is_file():
            raise ValueError('Missing compiler input: ' + rel)
    out.mkdir(exist_ok=False)
    inputs = out / 'inputs'
    pins = {}
    headers = sorted(p for p in (ROOT / 'hardware/deps/common_cells/include').rglob('*') if p.is_file())
    for source in [*(ROOT / rel for rel in SOURCES), *headers]:
        destination = inputs / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = sha(source)
        shutil.copyfile(source, destination)
        if sha(destination) != expected:
            raise ValueError('Snapshot race: ' + str(source))
        pins[str(source)] = pins[str(destination)] = expected
    for name in ('run_vmfpu.py', 'vmfpu_tb.sv'):
        source, destination = HERE / name, inputs / name
        expected = sha(source)
        shutil.copyfile(source, destination)
        if sha(destination) != expected:
            raise ValueError('Snapshot race: ' + name)
        pins[str(source)] = pins[str(destination)] = expected
    filelist = inputs / 'sources.f'
    filelist.write_text('+incdir+' + str(inputs / 'hardware/deps/common_cells/include') + '\n' +
        '\n'.join(str(inputs / rel) for rel in SOURCES) + '\n' + str(inputs / 'vmfpu_tb.sv') + '\n')
    pins[str(filelist)] = sha(filelist)
    save(out / 'source-pins.json', pins)
    save(out / 'config.json', dict(vcs=shutil.which('vcs'), timeout_seconds=300,
        revision=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        scope='Actual VMFPU; native integer instructions and exclusive borrowing; no FP/SoC/performance acceptance'))
    verify(pins)
    print(inputs / 'run_vmfpu.py')


def check(text):
    if re.search(r'(?im)(?:^Error-|^Error:|^Fatal:|Assertion failed|\$fatal)', text):
        raise ValueError('Simulator error')
    rows = re.findall(r'^STAGE2_VMFPU_PASS native=(\d+) borrowed=(\d+) returned=(\d+) '
                      r'cancelled=(\d+) acquires=(\d+) releases=(\d+) collisions=(\d+)$', text, re.M)
    if len(rows) != 1:
        raise ValueError('Missing/duplicate VMFPU terminal PASS')
    native, accepted, returned, cancelled, acquires, releases, collisions = map(int, rows[0])
    if native != 10 or accepted != returned + cancelled or returned < 250 or (
            acquires, releases, collisions) != (3, 2, 9):
        raise ValueError('Incomplete test coverage or response accounting')
    return dict(native=native, borrowed=accepted, returned=returned, cancelled=cancelled,
                acquires=acquires, releases=releases, collisions=collisions)


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/run_vmfpu.py':
        raise ValueError('Execute frozen runner only')
    config = json.loads((out / 'config.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    report = dict(state='FAIL', configurations=[], scope=config['scope'])
    try:
        verify(pins)
        for shared in (0, 1):
            work = out / f'shared{shared}'
            work.mkdir(exist_ok=False)
            argv = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                    '-top', 'stage2_vmfpu_tb', '-o', 'simv', '-f', str(out / 'inputs/sources.f')]
            if shared:
                argv.append('+define+ARA_SHARED_SIMD_MUL')
            save(work / 'commands.json', dict(compile=argv, run=[str(work / 'simv'), '-no_save']))
            for label, command in (('compile', argv), ('run', [str(work / 'simv'), '-no_save'])):
                print(f'STAGE2_VMFPU_{label.upper()} shared={shared}', flush=True)
                with (work / f'{label}.log').open('w') as stream:
                    subprocess.run(command, cwd=work, stdout=stream, stderr=subprocess.STDOUT,
                                   timeout=config['timeout_seconds'], check=True)
                verify(pins)
            row = check((work / 'run.log').read_text())
            row['shared'] = shared
            report['configurations'].append(row)
            images = {str(p): sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
            images[str(work / 'simv')] = sha(work / 'simv')
            save(work / 'image-pins.json', images)
        verify(pins)
        report.update(state='PASS', source_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    save(out / 'report.json', report)
    print('STAGE2_VMFPU_' + report['state'], flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        return execute(args.output.resolve())
    prepare(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
