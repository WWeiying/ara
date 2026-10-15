#!/usr/bin/env python3
"""Replay approved fast ports on a retained image; never snapshot or build RTL.

Without --execute, only write a pinned plan in a fresh output directory.
Run this worker directly under systemd with KillMode=control-group.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
PIPELINE_SHA = '7b9bf25b6b86a67966bc08539b5d552f8317aa71a886a95275d66ae4326c17f0'
FAST_SHA = '46e20a70677f3d62ae555e9e82cad725b165eb522a9bf17c0bf57a4b34c27626'
PROGRAMS_SHA = 'e2dbc0f8ce366245c04bfbc0e1eb6d6bcce7d5df8cee10ccf41e14f85f1daf83'


def load_pipeline():
    path = BASE / 'run_pipeline.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != PIPELINE_SHA:
        raise ValueError('sealed pipeline drift')
    spec = importlib.util.spec_from_file_location('sealed_replay_pipeline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args(pipeline, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--programs', type=Path, default=Path('/tmp/current-board-integration-fast01/soc'))
    parser.add_argument('--smokes', type=Path, default=Path('/tmp/current-board-integration-smoke01'))
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--timeout', type=int, choices=[300], default=300)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    for name in ('image', 'out', 'programs', 'smokes'):
        setattr(args, name, getattr(args, name).resolve())
    args.snapshot = Path(pipeline.read(args.image / 'image.json')['snapshot']).resolve()
    args.build_timeout = 1200  # Original stage factory requires this; build stage is discarded.
    for source in (HERE, BASE, args.image, args.snapshot, args.programs, args.smokes):
        if args.out == source or args.out in source.parents or source in args.out.parents:
            parser.error('output must be independent of retained image and input directories')
    return args


def configure(pipeline, args):
    original_inputs, original_stages = pipeline.inputs, pipeline.stages

    def inputs(options):
        pins = original_inputs(options)
        pipeline.pin(pins, __file__)
        receipt = HERE / 'SHA256SUMS'
        pipeline.pin(pins, receipt, FAST_SHA)
        for line in receipt.read_text().splitlines():
            digest, name = line.split('  ', 1)
            pipeline.pin(pins, HERE / name, digest)
        pipeline.pin(pins, options.programs / 'programs.json', PROGRAMS_SHA)
        ledger_path = options.image / 'image.json'
        pipeline.pin(pins, ledger_path)
        ledger = pipeline.read(ledger_path)
        if Path(ledger['snapshot']).resolve() != options.snapshot:
            raise ValueError('image snapshot identity changed')
        pipeline.pin(pins, options.snapshot / 'snapshot.json', ledger['snapshot_sha256'])
        metadata = options.image / 'run.json'
        pipeline.pin(pins, metadata)
        if pipeline.read(metadata)['status'] != 'BUILT':
            raise ValueError('retained image was not BUILT')
        simv = Path(ledger['simv'])
        if str(simv) not in ledger['files']:
            raise ValueError('simulator missing from image pins')
        for path, digest in ledger['files'].items():
            pipeline.pin(pins, path, digest)
        pipeline.pin(pins, simv.parent / 'simulator.conf', ledger['configuration_sha256'])
        pipeline.pin(pins, simv.parent / 'vcs_source_manifest.json', ledger['manifest_sha256'])
        return pins

    def stages(options):
        result = original_stages(options)[1:]
        if [s['name'] for s in result] != ['singles', 'combined', 'extended', 'gather', 'smokes']:
            raise ValueError('unexpected inherited stage order')
        for stage in result:
            command = stage['argv']
            command[command.index('--image') + 1] = str(options.image)
            stage['command'] = shlex.join(command)
            if 'build-image' in command or '--authorize-build' in command:
                raise ValueError('replay must not build')
        return result

    # Adapt this private imported module before main freezes plan/status. No
    # file mutation or changes to acceptance, cancellation or execution logic.
    pipeline.parse_args = lambda: args
    pipeline.inputs = inputs
    pipeline.stages = stages
    return pipeline


def main():
    pipeline = load_pipeline()
    return configure(pipeline, parse_args(pipeline)).main()


if __name__ == '__main__':
    raise SystemExit(main())
