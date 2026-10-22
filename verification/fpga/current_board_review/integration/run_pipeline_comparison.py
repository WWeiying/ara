#!/usr/bin/env python3
"""Successor acceptance entry; do not change the earlier sealed pipeline."""
from pathlib import Path
import math
import shlex
import sys
import run_pipeline as pipeline


pipeline.RTL = {
    'hardware/src/ara.sv': '1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da',
    'hardware/src/ara_dispatcher.sv': '4eda3df195e1a8ec319e51a14df1a051964cd08f6ee10335145a7c10cc89db4d',
    'hardware/src/lane/lane_sequencer.sv': '60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0',
    'hardware/src/lane/vmfpu.sv': 'e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12',
    'hardware/src/masku/masku.sv': '1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d',
    'hardware/src/masku/masku_operands.sv': 'c907488c75b5051a917e61c5ac08bca15859f2f0506fd61dae07dd576569456f',
    'hardware/src/sldu/sldu.sv': '1908da4368316c0979e388e934cf04dacf2d266297b36d35b1a803222d2a311e',
}
original_inputs = pipeline.inputs
original_stages = pipeline.stages
REVIEW = Path(__file__).resolve().parent.parent
EXTRA = (
    ('comparison', REVIEW / 'comparison/soc',
     ('active_snan', 'no_snan', 'all_off', 'tail_vl15', 'prestart_snan')),
    ('comparison-matrix', REVIEW / 'comparison/soc_matrix',
     ('prefix_quiet_tail', 'matrix_e16', 'matrix_e32', 'matrix_e64')),
    ('flags-sequence', Path('/tmp/current-board-flags-sequence02/soc'), ('flags_sequence',)),
    ('reduction-epoch', REVIEW / 'reduction_epoch/measurement01/soc', ('all',)),
)


def inputs(args):
    pins = original_inputs(args)
    pipeline.pin(pins, Path(__file__).resolve())
    pipeline.pin(pins, Path(__file__).with_name('smoke_scalar.py'))
    for _, directory, names in EXTRA:
        pipeline.pin(pins, directory / 'programs.json')
        programs = pipeline.read(directory / 'programs.json')
        if programs['backend'] != 'vcs-soc':
            raise ValueError('SoC ELF ledger required: ' + str(directory))
        provenance = Path(programs['prepared']) / 'provenance.json'
        pipeline.pin(pins, provenance, programs['provenance_sha256'])
        for name, digest in pipeline.read(provenance)['files'].items():
            pipeline.pin(pins, provenance.parent / name, digest)
        for name in names:
            program = programs['programs'][name]
            pipeline.pin(pins, program['path'], program['sha256'])
    return pins


def stages(args):
    result = original_stages(args)
    for name, programs, cases in EXTRA:
        out = args.out / name
        command = [str(Path(sys.executable).resolve()), str(pipeline.HERE / 'run.py'),
                   'run', '--image', str(args.out / 'image'), '--programs', str(programs),
                   '--out', str(out), '--jobs', str(args.jobs),
                   '--timeout', str(args.timeout), '--execute']
        for case in cases:
            command += ['--case', case]
        result.append(dict(name=name, cases=list(cases), out=str(out),
                           timeout_s=math.ceil(len(cases) / args.jobs) * args.timeout + 120,
                           status='PENDING', argv=command, command=shlex.join(command),
                           log=str(args.out / (name + '.log'))))
    return result


pipeline.inputs = inputs
pipeline.stages = stages

if __name__ == '__main__':
    raise SystemExit(pipeline.main())
