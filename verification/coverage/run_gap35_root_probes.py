#!/usr/bin/env python3
"""Reproduce two historical failures on the current image with existing probes."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
import subprocess

import run_vcs_dve_checkpoint as base

ROOT = base.ROOT
IMAGE_RUN = ROOT / 'verification/out/qbs-fault-layout-repair-20261005-01'
OLD = ROOT / 'verification/out/gap35-vector-checked-preflight-20261004-03'
NAMES = ('vgap35_carry_ta', 'vgap35_slide_bound')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base.check_service()
    out = base.checked_output(args.output)
    out.mkdir(exist_ok=False)
    image = IMAGE_RUN / 'image/sim/simv'
    pins = base.read(IMAGE_RUN / 'regression-source-pins.json')
    pins.update(base.read(IMAGE_RUN / 'image/build-image.json'))
    pins.update(base.pins([Path(__file__), OLD / 'plan.json']))
    plan = base.read(OLD / 'plan.json')
    state = dict(status='PREPARING', phase='freeze', total=2, cases={},
                 workers=2, verified_coverage_admission=False)
    base.save(out / 'status.json', state)
    for name in NAMES:
        record = next(row for row in plan['cases'] if row['name'] == name)
        elf = Path(record['frozen_elf'])
        base.check({str(elf): record['elf_sha256']})
        for source, expected in record['source_files'].items():
            if source.endswith((name + '.c', 'vgap35_common.h')):
                base.check({source: expected})
                pins[source] = expected
        directory = out / 'results' / name
        directory.mkdir(parents=True)
        shutil.copyfile(elf, directory / 'input.elf')
        pins.update(base.pins([directory / 'input.elf']))
        state['cases'][name] = dict(status='RUNNING', directory=str(directory))
    base.check(pins)
    base.save(out / 'source-pins.json', pins)
    state.update(status='RUNNING', phase='two discriminating probe simulations')
    base.save(out / 'status.json', state)

    def run(name):
        directory = out / 'results' / name
        flags = (['+ARA_DEBUG_MASK_CARRY', '+ARA_DEBUG_MASK_VSTART',
                  '+ARA_DEBUG_MASKB', '+ARA_DEBUG_DEP_CHAIN']
                 if name.endswith('carry_ta') else
                 ['+ARA_DEBUG_SLIDE_MASK', '+ARA_DEBUG_LAYOUT428_DATA'])
        command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB',
                   '+PRELOAD=' + str(directory / 'input.elf'),
                   '+TESTCASE=' + name,
                   '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
                   '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'),
                   '-cm', 'line+cond+fsm+tgl+branch',
                   '-cm_dir', str(directory / 'diagnostic.vdb'), '-cm_name', name,
                   *flags]
        base.save(directory / 'command.json', dict(command=command, timeout_s=1800))
        try:
            with (directory / 'console.log').open('w') as stream:
                result = subprocess.run(command, cwd=directory, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=1800)
            base.check(pins)
            log = (directory / 'run.vcs.log').read_text()
            if 'gap35 checks=' not in log:
                raise RuntimeError('test did not reach its complete self-check summary')
            row = dict(status='PROBE_COMPLETE', returncode=result.returncode,
                       directory=str(directory),
                       summaries=[line for line in log.splitlines()
                                  if 'gap35 checks=' in line or 'check=' in line],
                       verified_coverage_admission=False)
        except Exception as error:
            row = dict(status='PROBE_ERROR', reason=str(error), directory=str(directory))
        base.save(directory / 'probe-result.json', row)
        return name, row

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(run, name) for name in NAMES]):
            name, row = future.result()
            state['cases'][name] = row
            base.save(out / 'status.json', state)
    state.update(status='COMPLETE', phase='root-cause review required')
    base.save(out / 'status.json', state)


if __name__ == '__main__':
    main()
