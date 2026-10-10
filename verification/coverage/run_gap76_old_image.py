#!/usr/bin/env python3
"""Extend the frozen 654-PASS image, without rebuilding or reverting live RTL."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import subprocess

import run_gap75_operand_batch as helpers
import coverage_bitmap_delta as bitmaps

base = helpers.base
ROOT = base.ROOT
BASELINE = ROOT / 'verification/out/closure90-current-20261005-01'
NEW = ['vgap76_' + op + sew for op in ('mul', 'add', 'sub', 'red') for sew in ('16', '32')]
NAMES = [*NEW, *helpers.NAMES]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--cases', nargs='+', choices=[*NAMES,
        'vgap77_onehot16', 'vgap77_onehot32', 'vgap77_dense16', 'vgap77_dense32',
        'vgap78_add16', 'vgap78_add32', 'vgap78_sub16', 'vgap78_sub32'])
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    names = args.cases or NAMES
    if len(set(names)) != len(names):
        parser.error('duplicate case names')
    base.check_service()
    out = base.checked_output(args.output)
    out.mkdir(exist_ok=False)
    state = dict(status='PREPARING', phase='freeze old image and compile stimulus',
                 cases={}, total=len(names), workers=8, baseline_passed=None,
                 live_rtl_reverted=False, coverage_status='PENDING')
    def save(): base.save(out / 'status.json', state)
    save()
    try:
        state_file = baseline / ('checkpoint.json' if baseline == BASELINE else 'status.json')
        baseline_state = base.read(state_file)
        if baseline_state.get('coverage_status') != 'COMPLETE':
            raise RuntimeError('completed PASS-only baseline required')
        population = baseline_state['aggregate_passed']
        plan = base.read(BASELINE / 'plan.json')
        image = Path(plan['simv'])
        design = Path(plan['design_vdb'])
        baseline_inputs = (baseline / 'combined-inputs.txt').read_text().splitlines()
        if Path(baseline_inputs[0]) != design or len(baseline_inputs) != population + 1:
            raise RuntimeError('baseline design or PASS-only population differs')
        if len(set(baseline_inputs)) != len(baseline_inputs):
            raise RuntimeError('duplicate baseline VDB')
        state['baseline_passed'] = population
        state['baseline_directory'] = str(baseline)
        pins = dict(plan['image'])
        base.check(pins)
        pins.update(base.pins([Path(__file__), Path(helpers.__file__), Path(bitmaps.__file__),
            BASELINE / 'checkpoint.json', BASELINE / 'collection.json', BASELINE / 'plan.json',
            BASELINE / 'combined-inputs.txt', BASELINE / 'combined-bits.json', helpers.SPIKE,
            ROOT / 'verification/ara_verify/spike_trace.py',
            ROOT / 'verification/ara_verify/vector_commit.py',
            ROOT / 'verification/coverage/run_dve_coverage.sh',
            ROOT / 'verification/coverage/export_dve_coverage.tcl']))
        pins.update(base.pins([state_file, baseline / 'combined-inputs.txt',
                              baseline / 'combined-bits.json']))
        compiler = Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin/clang')
        readelf = compiler.parent / 'llvm-readelf'
        startup = ROOT / 'verification/tests/gap75_start.S'
        linker = ROOT / 'verification/tests/gap75.ld'
        source = ROOT / 'apps/riscv-tests/isa/rv64uv'
        pins.update(base.pins([compiler, readelf, startup, linker,
            source / 'vgap76_wide_body.h', source / 'vgap75_ext_body.h', source / 'vgap75_red_body.h']))
        pins.update(base.pins(source / (n + '.c') for n in names))
        for name in names:
            directory = out / 'results' / name
            directory.mkdir(parents=True)
            command = [str(compiler), '--target=riscv64-unknown-elf', '-march=rv64gcv_zfh_zvfh',
                '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0',
                '-O2', '-fno-vectorize', '-fno-slp-vectorize', '-ffreestanding',
                '-DG75_NO_PRINT', '-D__SPIKE__', '-DVLEN=1024', '-DNR_LANES=4',
                '-I' + str(ROOT / 'apps/riscv-tests/isa/macros/vector'),
                '-I' + str(ROOT / 'apps/riscv-tests/env'), '-I' + str(ROOT / 'apps/common'),
                '-fuse-ld=lld', '-nostdlib', '-T' + str(linker), str(startup),
                str(source / (name + '.c')), '-o', str(directory / 'input.elf')]
            base.save(directory / 'compile.command.json', dict(command=command))
            with (directory / 'compile.log').open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
            data = (directory / 'input.elf').read_bytes()
            if helpers.struct.unpack_from('<Q', data, 24)[0] != 0x80000000:
                raise RuntimeError('incorrect ELF boot entry')
            phoff = helpers.struct.unpack_from('<Q', data, 32)[0]
            phsize, phnum = helpers.struct.unpack_from('<HH', data, 54)
            for i in range(phnum):
                seg = helpers.struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize)
                if seg[0] == 1 and seg[5] and seg[4] % 128:
                    raise RuntimeError('unaligned preload segment')
            pins.update(base.pins([directory / 'input.elf']))
        base.check(pins)
        base.save(out / 'source-pins.json', pins)
        state.update(status='RUNNING', phase='Spike preflight then eight VCS workers',
            image=str(image), cases={n: dict(status='QUEUED') for n in names})
        save()

        def run(name):
            directory = out / 'results' / name
            elf = directory / 'input.elf'
            row = dict(status='RUNNING', directory=str(directory))
            try:
                spike = [str(helpers.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b',
                         '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(elf)]
                base.save(directory / 'spike.command.json', dict(command=spike, timeout_s=120))
                with (directory / 'spike.stdout').open('w') as stdout, (directory / 'spike.trace').open('w') as stderr:
                    subprocess.run(spike, stdout=stdout, stderr=stderr, timeout=120, check=True)
                tohost = helpers._elf_symbol(elf, readelf, 'tohost')
                signature = helpers._elf_symbol(elf, readelf, 'g75_result')
                writes = {addr: value for c in helpers.parse_spike_commits(directory / 'spike.trace')
                          for addr, value in c.memory_accesses if value is not None}
                if writes.get(tohost) != 1 or not writes.get(signature, 0) or writes.get(signature + 4) != 0:
                    raise RuntimeError('Spike self-check failed; no VCS admission')
                command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
                    '+PRELOAD=' + str(elf), '+TESTCASE=' + name, '+COMMIT_TOHOST=%x' % tohost,
                    '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
                    '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'),
                    '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(directory / 'code.vdb'), '-cm_name', name]
                base.save(directory / 'rtl.command.json', dict(command=command, timeout_s=1800))
                with (directory / 'console.log').open('w') as log:
                    subprocess.run(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=1800, check=True)
                entry = 0x80000000
                scalar = helpers.compare_commit_prefix(directory / 'spike.trace', directory / 'commit_trace.csv',
                    entry, terminal_tohost_address=tohost, rvfi_store_data_layout='unshifted')
                vector = helpers.compare_vector_commits(directory / 'spike.trace', directory / 'commit_trace.csv',
                    directory / 'vector_trace.csv', entry)
                base.save(directory / 'scalar-comparison.json', scalar)
                base.save(directory / 'vector-comparison.json', vector)
                if scalar['status'] not in ('MATCH', 'TERMINAL_TOHOST_MATCH') or vector['status'] != 'PASS':
                    raise RuntimeError('complete scalar/vector differential mismatch')
                if helpers.check_contract_log(directory / 'run.vcs.log') or 'Core Test *** SUCCESS ***' not in (directory / 'run.vcs.log').read_text():
                    raise RuntimeError('DUT self-check or contract failed')
                base.check(pins)
                row.update(status='PASS', checks=writes[signature], vector_bytes=vector['compared_bytes'],
                           vdb=str(directory / 'code.vdb'))
            except Exception as error:
                row.update(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
                           reason=f'{type(error).__name__}: {error}')
            base.save(directory / 'audit.json', row)
            return name, row

        with ThreadPoolExecutor(max_workers=8) as pool:
            for future in as_completed([pool.submit(run, n) for n in names]):
                name, row = future.result()
                state['cases'][name] = row
                save()
        passed = [state['cases'][n]['vdb'] for n in names if state['cases'][n]['status'] == 'PASS']
        state.update(phase='PASS-only coverage export', new_passed=len(passed))
        save()
        if passed:
            listing = out / 'new-inputs.txt'
            listing.write_text('\n'.join([str(design), *passed]) + '\n')
            new_bits = bitmaps.collect(listing)
            combined = bitmaps.combine(base.read(baseline / 'combined-bits.json'), new_bits)
            base.save(out / 'combined-bits.json', combined)
            base.save(out / 'raw-bitmap-delta.json', bitmaps.delta(base.read(baseline / 'combined-bits.json'), combined))
            listing = out / 'combined-inputs.txt'
            listing.write_text('\n'.join([*baseline_inputs, *passed]) + '\n')
            with (out / 'dve.log').open('w') as log:
                subprocess.run(['bash', str(ROOT / 'verification/coverage/run_dve_coverage.sh'),
                    str(out / 'combined-dve'), '--inputs-file', str(listing)], cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT, timeout=1260,
                    env=dict(os.environ, DVE_COVERAGE_TIMEOUT='1200', DVE_WAIVERS='off'), check=True)
        base.check(pins)
        state.update(status='COMPLETE', phase='complete', aggregate_passed=population + len(passed),
                     coverage_status='COMPLETE' if passed else 'NO_NEW_PASS',
                     scope='old frozen RTL only; raw DVE, no new-RTL VDBs')
        save()
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        save()
        raise


if __name__ == '__main__':
    main()
