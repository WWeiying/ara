#!/usr/bin/env python3
"""One pinned image, two restart reproducers and thirteen bounded regressions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import build_memory_vl0_repair as builder
import run_qbs_fault_layout_repair as custom
import run_gap75_operand_batch as operands

base = builder.base
ROOT = base.ROOT
PROBES = ROOT / 'verification/out/gap35-root-probes-20261005-01'
OPERANDS = ROOT / 'verification/out/gap75-operand-20261005-04'
CUSTOM = ROOT / 'verification/out/qbs-fault-layout-repair-20261005-01'
COUNTS = {'vgap35_carry_ta': 459, 'vgap35_slide_bound': 535}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base.check_service()
    out = base.checked_output(args.output)
    out.mkdir(exist_ok=False)
    state = dict(status='BUILDING', phase='independent VCS image', cases={},
                 total=15, workers=5, old_vdb_reuse=False)
    def save(): base.save(out / 'status.json', state)
    save()
    try:
        sys.argv = [builder.__file__, '--output', str(out / 'image'),
                    '--approved-dispatcher-sha256', base.sha256(builder.DISPATCHER)]
        builder.main()
        image = out / 'image/sim/simv'
        pins = base.read(out / 'image/build-source-pins.json')
        pins.update(base.read(out / 'image/build-image.json'))
        pins.update(base.pins([Path(__file__), Path(custom.__file__), Path(operands.__file__)]))
        names = [*COUNTS, *custom.NAMES, *operands.NAMES]
        for name in names:
            origin = PROBES if name in COUNTS else CUSTOM if name in custom.NAMES else OPERANDS
            src = origin / 'results' / name
            if name in operands.NAMES and base.read(src / 'audit.json')['status'] != 'PASS':
                raise RuntimeError('operand source did not pass its independent checker')
            directory = out / 'results' / name
            directory.mkdir(parents=True)
            shutil.copyfile(src / 'input.elf', directory / 'input.elf')
            if name in operands.NAMES:
                shutil.copyfile(src / 'spike.trace', directory / 'spike.trace')
                pins.update(base.pins([directory / 'spike.trace']))
            pins.update(base.pins([src / 'input.elf', directory / 'input.elf']))
        base.check(pins)
        base.save(out / 'regression-source-pins.json', pins)
        state.update(status='RUNNING', phase='restart repair and representative regression',
                     cases={name: dict(status='QUEUED') for name in names})
        save()

        def run(name):
            directory = out / 'results' / name
            elf = directory / 'input.elf'
            command = [str(image), '-l', 'run.vcs.log', '+ntb_random_seed=1', '+NO_FSDB',
                       '+PRELOAD=' + str(elf), '+TESTCASE=' + name,
                       '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
                       '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'),
                       '-cm', 'line+cond+fsm+tgl+branch',
                       '-cm_dir', str(directory / 'code.vdb'), '-cm_name', name]
            tohost = None
            if name in operands.NAMES:
                readelf = Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readelf')
                tohost = operands._elf_symbol(elf, readelf, 'tohost')
                command.append('+COMMIT_TOHOST=%x' % tohost)
            if name in custom.NAMES:
                command.append('+QBS_PERF' if 'qbs' in name else '+AKV_PERF')
            base.save(directory / 'command.json', dict(command=command, timeout_s=1800))
            row = dict(status='RUNNING', directory=str(directory))
            try:
                with (directory / 'console.log').open('w') as stream:
                    subprocess.run(command, cwd=directory, stdout=stream,
                                   stderr=subprocess.STDOUT, timeout=1800, check=True)
                base.check(pins)
                log = (directory / 'run.vcs.log').read_text()
                if operands.check_contract_log(directory / 'run.vcs.log'):
                    raise RuntimeError('RTL contract failure')
                if name in custom.NAMES:
                    evidence = custom.audit(directory, name)
                elif name in COUNTS:
                    summaries = re.findall(r'gap35 checks=(\d+) failures=(\d+)', log)
                    if summaries != [(str(COUNTS[name]), '0')] or 'Core Test *** SUCCESS ***' not in log:
                        raise RuntimeError('complete scalar self-check did not pass: ' + str(summaries))
                    evidence = dict(checks=COUNTS[name], failures=0,
                        oracle='frozen scalar carry/borrow or slide reference; not instruction differential',
                        trace=operands.validate_trace(directory / 'commit_trace.csv'))
                else:
                    entry = operands.struct.unpack_from('<Q', elf.read_bytes(), 24)[0]
                    scalar = operands.compare_commit_prefix(directory / 'spike.trace',
                        directory / 'commit_trace.csv', entry, terminal_tohost_address=tohost,
                        rvfi_store_data_layout='unshifted')
                    vector = operands.compare_vector_commits(directory / 'spike.trace',
                        directory / 'commit_trace.csv', directory / 'vector_trace.csv', entry)
                    base.save(directory / 'scalar-comparison.json', scalar)
                    base.save(directory / 'vector-comparison.json', vector)
                    if scalar['status'] not in ('MATCH', 'TERMINAL_TOHOST_MATCH') or vector['status'] != 'PASS':
                        raise RuntimeError('strict scalar/vector comparison failed')
                    if 'Core Test *** SUCCESS ***' not in log:
                        raise RuntimeError('operand self-check failed')
                    evidence = dict(scalar=scalar['status'], vector='PASS')
                row.update(status='PASS', evidence=evidence, vdb=str(directory / 'code.vdb'))
            except Exception as error:
                row.update(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
                           reason=f'{type(error).__name__}: {error}')
            base.save(directory / 'audit.json', row)
            return name, row

        with ThreadPoolExecutor(max_workers=5) as pool:
            for future in as_completed([pool.submit(run, n) for n in names]):
                name, row = future.result()
                state['cases'][name] = row
                save()
        base.check(pins)
        state.update(status='PASS' if all(r['status'] == 'PASS' for r in state['cases'].values()) else 'FAIL',
                     phase='regression complete', scope='15 bounded tests, not full signoff',
                     coverage_status='VDB collected; no old-RTL merge')
        save()
        return 0 if state['status'] == 'PASS' else 1
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        save()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
