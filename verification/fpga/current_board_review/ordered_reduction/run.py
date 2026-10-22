#!/usr/bin/env python3
"""Snapshot real VMFPU/FPnew and replay bounded ordered-reduction interface tests."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
ORIGINAL = CAMPAIGN / 'rvv_verified_handoff03/rvv_small_redspecial02'
DEPLOYED = CAMPAIGN / 'rvv_verification_handoff02/deployed_rtl/vmfpu.sv'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cases(extended):
    result = []

    def add(name, width, vl, mask, vm=0, rm=0, prior=0, mode=0, stalls=0):
        selected = [i for i in range(vl) if vm or mask >> (i % 32) & 1]
        if mode == 2:
            # All selected operands are exactly 1, with +0 seed; sums <= 256.
            count = len(selected)
            fraction, bias = (10, 15) if width == 16 else (23, 127)
            exponent = count.bit_length()-1
            bits = 0 if not count else ((bias+exponent) << fraction) | ((count-(1 << exponent)) << (fraction-exponent))
            flags = prior
        else:
            invalid = bool(selected) if mode == 1 else any(i % 2 for i in selected)
            bits = (0x7e00 if width == 16 else 0x7fc00000) if invalid else (0x7c00 if width == 16 else 0x7f800000)
            flags = prior | (16 if invalid else 0)
        result.append(dict(name=name, width=width, vl=vl, mask=mask, vm=vm, rm=rm,
                           prior=prior, mode=mode, stalls=stalls, bits=bits, flags=flags))

    for width in (32, 16):
        length = 512 // width
        add(f'original_e{width}_m1', width, length, 0x24242424)
        add(f'first_slot_e{width}', width, length, 0x02020202)
        add(f'all_off_e{width}', width, length, 0)
        add(f'unmasked_e{width}', width, length, 0, vm=1)
    if extended:
        for path in sorted(ORIGINAL.glob('*/case.json')):
            entry = json.loads(path.read_text())
            width, length = entry['case']['sew'], entry['evidence']['tuple']['vl']
            for rm in range(5):
                for prior in (0, 1):
                    add(f'{path.parent.name}_rm{rm}_sticky{prior}', width, length,
                        0x24242424, rm=rm, prior=prior, stalls=1)
        for width in (16, 32):
            for slot in range(64 // width):
                add(f'isolated_e{width}_slot{slot}', width, 4*(64//width), 1 << (4*slot+1), stalls=1)
            for length in (5, 7, 8, 9, 15, 16, 17, 31, 32):
                add(f'tail_e{width}_vl{length}', width, length, 0x24242424, stalls=1)
                add(f'finite_e{width}_vl{length}', width, length, 0x24242424, mode=2, stalls=1)
            add(f'inactive_snan_e{width}', width, 16, 0, mode=1, prior=1, stalls=1)
            add(f'positive_only_e{width}', width, 16, 0x55555555, stalls=1)
            add(f'all_on_e{width}', width, 16, 0xffffffff, stalls=1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--vmfpu', type=Path, help='default: current RTL; may select archived deployed RTL')
    parser.add_argument('--extended', action='store_true')
    parser.add_argument('--fsdb', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins = {}

    def snapshot(path, source=None):
        src = source or ROOT / path
        dst = out / 'inputs' / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dst.write_bytes(data)
        dst.chmod(0o444)
        pins[path] = dict(source=str(src), sha256=sha(data))
        return str(dst)

    packages = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
                'hardware/deps/axi/src/axi_pkg.sv',
                'hardware/deps/cva6/core/include/config_pkg.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                'hardware/deps/cva6/core/include/riscv_pkg.sv',
                'hardware/deps/cva6/core/include/ariane_pkg.sv',
                'hardware/deps/cva6/core/include/build_config_pkg.sv',
                'hardware/include/rvv_pkg.sv',
                'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
    files = packages + [f'hardware/deps/common_cells/src/{name}.sv' for name in
                       ['spill_register_flushable', 'spill_register', 'lzc', 'rr_arb_tree']]
    files += ['hardware/deps/tech_cells_generic/src/rtl/tc_clk.sv',
              'hardware/src/lane/power_gating_generic.sv',
              'hardware/deps/cva6/core/serdiv.sv', 'hardware/src/lane/simd_mul.sv',
              'hardware/src/lane/simd_div.sv']
    files += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'hardware/deps/fpnew/src').glob('*.sv'))
              if p.name != 'fpnew_pkg.sv']
    vendor = ROOT / 'hardware/deps/fpnew/vendor'
    files += [str(p.relative_to(ROOT)) for p in sorted((vendor / 'openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl').glob('*.v'))]
    files += [str((vendor / 'opene906/E906_RTL_FACTORY/gen_rtl/clk/rtl/gated_clk_cell.v').relative_to(ROOT))]
    sources = [snapshot(path) for path in files]
    sources += [snapshot('hardware/src/lane/vmfpu.sv', args.vmfpu.resolve() if args.vmfpu else None),
                snapshot(str((HERE / 'ordered_reduction_tb.sv').relative_to(ROOT)))]
    for directory in ['hardware/include/ara', 'hardware/deps/common_cells/include/common_cells']:
        for path in sorted((ROOT / directory).glob('*.svh')):
            snapshot(str(path.relative_to(ROOT)))
    snapshot(str(Path(__file__).resolve().relative_to(ROOT)))
    snapshot(str((HERE / 'README.md').relative_to(ROOT)))
    for name in ('analyze.py', 'check_original_fixture.c', 'test_cases.py'):
        snapshot(str((HERE / name).relative_to(ROOT)))
    for path in sorted(ORIGINAL.glob('*/case.json')):
        snapshot('original/' + path.parent.name + '/case.json', path)
    for name in ('scenario.c', 'operations.S', 'fp_reduction_inputs.h', 'input_bits.h', 'fixtures.h'):
        for width in (16, 32):
            path = ORIGINAL / f'rvv_small_fp_redspecial_e{width}_m1' / name
            snapshot(f'original/e{width}/' + name, path)
    suite = cases(args.extended)
    (out / 'cases.json').write_text(json.dumps(suite, indent=2) + '\n')
    (out / 'inputs/cases.svh').write_text('\n'.join(
        f'run_case({i}, "{c["name"]}", {c["width"]}, {c["vl"]}, 32\'h{c["mask"]:08x}, '
        f'1\'b{c["vm"]}, {c["rm"]}, {c["prior"]}, {c["mode"]}, {c["stalls"]}, '
        f'64\'h{c["bits"]:016x}, 5\'h{c["flags"]:02x});' for i, c in enumerate(suite)) + '\n')
    pins['cases.svh'] = dict(source='generated from cases.json', sha256=sha((out / 'inputs/cases.svh').read_bytes()))
    (out / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi = '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    env = dict(os.environ, VCS_HOME=vcs, VERDI_HOME=verdi, SNPSLMD_LICENSE_FILE='27000@t7920')
    env['PATH'] = vcs + '/bin:' + env['PATH']
    command = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-debug_access+all', '-top', 'ordered_reduction_tb',
               '+incdir+' + str(out / 'inputs/hardware/deps/common_cells/include'),
               '+incdir+' + str(out / 'inputs/hardware/include'), '+incdir+' + str(out / 'inputs'),
               '-P', verdi + '/share/PLI/VCS/LINUX64/novas.tab',
               verdi + '/share/PLI/VCS/LINUX64/pli.a',
               *sources, '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    status = dict(state='STARTED', start=time.time(), scope='four real VMFPUs/FPnew; modeled slide, mask and operand delivery; no CPU/ELF/CSR',
                  vmfpu=pins['hardware/src/lane/vmfpu.sv'], case_count=len(suite))
    try:
        status['original_fixture_checks'] = []
        for width in (16, 32):
            fixture_binary = out / f'check_fixture{width}'
            fixture_command = ['gcc', '-Wall', '-Wextra', '-Werror', f'-DSEW={width}',
                               '-I' + str(out / f'inputs/original/e{width}'),
                               str(out / 'inputs' / HERE.relative_to(ROOT) / 'check_original_fixture.c'),
                               '-o', str(fixture_binary)]
            subprocess.run(fixture_command, check=True, capture_output=True, timeout=30)
            checked = subprocess.run([str(fixture_binary)], check=True, capture_output=True,
                                     text=True, timeout=10)
            status['original_fixture_checks'].append(dict(command=fixture_command, output=checked.stdout.strip()))
        with (out / 'compile.console.log').open('w') as log:
            result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        status['compile_exit'] = result.returncode
        if result.returncode:
            raise RuntimeError('VCS compile failed; inspect compile.console.log')
        run = [str(out / 'simv'), '-no_save'] + (['+FSDB'] if args.fsdb else [])
        (out / 'run_command.json').write_text(json.dumps(run, indent=2) + '\n')
        with (out / 'run.console.log').open('w') as log:
            result = subprocess.run(run, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        status['run_exit'] = result.returncode
        log = (out / 'run.console.log').read_text()
        with (out / 'results.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        if (result.returncode or re.search(r'(?m)^(?:Error|Fatal)(?:-|:|\[)', log) or
                f'ORDERED_REDUCTION_COMPLETE cases={len(suite)}' not in log or
                [r['name'] for r in rows] != [c['name'] for c in suite]):
            raise RuntimeError('Harness/simulator/accounting failure; inspect retained trace')
        status['failures'] = [r for r in rows if r['result_match'] != '1' or r['flags_match'] != '1']
        status['state'] = 'FAIL_ARCHITECTURAL_ORACLE' if status['failures'] else 'PASS_REDUCED_RTL'
        status['completed_cases'] = len(rows)
        status['evidence'] = {name: sha((out / name).read_bytes()) for name in
                              ('results.csv', 'trace.csv', 'run.console.log', 'simv')}
        status['runtime_objects'] = {str(p.relative_to(out)): sha(p.read_bytes())
                                     for p in sorted((out / 'simv.daidir').rglob('*.so'))}
        for name, pin in pins.items():
            if sha((out / 'inputs' / name).read_bytes()) != pin['sha256']:
                raise RuntimeError('Snapshot drift: ' + name)
    except Exception as exc:
        status.update(state='ERROR', error=repr(exc))
    status['finish'] = time.time()
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=2))
    return 0 if status['state'] == 'PASS_REDUCED_RTL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
