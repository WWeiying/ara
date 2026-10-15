#!/usr/bin/env python3
"""Sequential, fail-closed VCS pipeline consuming an already sealed snapshot.

No snapshot creation. Without --execute, write a pinned plan only. Run this
worker directly under systemd with KillMode=control-group; it never daemonizes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
RECEIPTS = {
    'SOURCE_SHA256SUMS': '568cbd184f4afadb3eff54cfe870cdb1bb81eb434bc2cb253537de7609e54d1d',
    'ARTIFACT_SHA256SUMS': '8d242b08d24f38b63f6841368acaf590db857a66cdcb38d80b9619e33d8336cb',
}
RTL = {
    'hardware/src/masku/masku.sv': '88692c2fc0edb6267d45edf43abce31b8e6be70e28a1e0adddc5dc1a11526a0d',
    'hardware/src/lane/lane_sequencer.sv': '60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0',
}
STAGES = (
    ('singles', ('maskslide', 'restart_compare', 'reduction_fflags', 'm8widen',
                 'wholemove', 'slide1up_prestart')),
    ('combined', ('all',)),
    ('extended', ('slide_source_e32', 'slide_source_e64', 'm8widen_nonzero',
                  'wholemove_layout', 'extended')),
    ('gather', ('gather_original', 'gather_prestart')),
    ('smokes', ('rvv_vadd', 'rvv_vslideup', 'rvv_vslidedown', 'rvv_vrgather',
                'rvv_vmseq', 'rvv_vfredosum', 'rvv_vfwredosum',
                'qbs_control_smoke', 'akv_context_smoke', 'qbs_akv_handoff_smoke')),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def pin(pins, path, expected=None):
    path = Path(path).resolve(strict=True)
    digest = sha(path)
    if expected is not None and digest != expected:
        raise ValueError('input hash mismatch: ' + str(path))
    if str(path) in pins and pins[str(path)] != digest:
        raise ValueError('input changed during pinning: ' + str(path))
    pins[str(path)] = digest


def inputs(args):
    pins = {}
    pin(pins, __file__)
    pin(pins, sys.executable)
    for name, digest in RECEIPTS.items():
        receipt = HERE / name
        pin(pins, receipt, digest)
        for line in receipt.read_text().splitlines():
            expected, filename = line.split('  ', 1)
            pin(pins, HERE / filename, expected)
    ledger = args.snapshot / 'snapshot.json'
    pin(pins, ledger)
    snapshot = read(ledger)
    if snapshot['state'] != 'SEALED':
        raise ValueError('snapshot is not SEALED')
    root = Path(snapshot['root'])
    for name, digest in snapshot['files'].items():
        source = root / name
        if source.is_symlink() or source.stat().st_mode & 0o222:
            raise ValueError('snapshot source is writable or symlinked: ' + str(source))
        pin(pins, source, digest)
    for name, digest in RTL.items():
        if snapshot['files'].get(name) != digest:
            raise ValueError('approved RTL identity missing from snapshot: ' + name)
    for directory, wanted in ((args.programs, [case for stage, cases in STAGES
                                             if stage != 'smokes' for case in cases]),
                              (args.smokes, STAGES[-1][1])):
        pin(pins, directory / 'programs.json')
        programs = read(directory / 'programs.json')
        if programs['backend'] != 'vcs-soc':
            raise ValueError('SoC ELFs required: ' + str(directory))
        prepared = Path(programs['prepared'])
        pin(pins, prepared / 'provenance.json', programs['provenance_sha256'])
        for name, digest in read(prepared / 'provenance.json')['files'].items():
            pin(pins, prepared / name, digest)
        for name in wanted:
            entry = programs['programs'][name]
            pin(pins, entry['path'], entry['sha256'])
    return pins


def verify(pins):
    for path, digest in pins.items():
        if sha(path) != digest:
            raise ValueError('pinned input drift: ' + path)


def stages(args):
    prefix = [str(Path(sys.executable).resolve()), str(HERE / 'run.py')]
    image = args.out / 'image'
    result = [dict(name='build-image', cases=[], out=str(image),
                   timeout_s=args.build_timeout, status='PENDING',
                   argv=prefix + ['build-image', '--snapshot', str(args.snapshot),
                                  '--out', str(image), '--authorize-build'])]
    for name, cases in STAGES:
        command = prefix + ['run', '--image', str(image), '--programs',
                            str(args.smokes if name == 'smokes' else args.programs),
                            '--out', str(args.out / name), '--jobs', str(args.jobs),
                            '--timeout', str(args.timeout), '--execute']
        for case in cases:
            command += ['--case', case]
        result.append(dict(name=name, cases=list(cases), out=str(args.out / name),
                           timeout_s=math.ceil(len(cases) / args.jobs) * args.timeout + 120,
                           status='PENDING', argv=command))
    for stage in result:
        stage['command'] = shlex.join(stage['argv'])
        stage['log'] = str(args.out / (stage['name'] + '.log'))
    return result


def acceptance(stage):
    directory = Path(stage['out'])
    metadata = read(directory / 'run.json')
    if stage['name'] == 'build-image':
        if metadata['status'] != 'BUILT':
            raise ValueError('build did not report BUILT')
        image = read(directory / 'image.json')
        if not image.get('files') or not Path(image['simv']).is_file():
            raise ValueError('missing reusable image')
    else:
        results = read(directory / 'summary.json')
        if metadata['status'] != 'COMPLETE':
            raise ValueError('stage did not complete normally')
        if sorted(r['name'] for r in results) != sorted(stage['cases']):
            raise ValueError('missing or duplicate case results')
        if any(r['status'] != 'PASS' or r['returncode'] != 0 for r in results):
            raise ValueError('not every required case passed')


def terminate(child):
    # A process group allows cleanup of descendants without leaving the service cgroup.
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def execute_stage(stage):
    with open(stage['log'], 'xb') as log:
        child = subprocess.Popen(stage['argv'], stdout=log, stderr=subprocess.STDOUT,
                                 cwd=HERE, start_new_session=True)
        try:
            return child.wait(timeout=stage['timeout_s'])
        finally:
            terminate(child)


def interrupted(signum, frame):
    raise InterruptedError('received signal ' + str(signum))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'programs', 'smokes', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--timeout', type=int, default=300, help='seconds per simulated program')
    parser.add_argument('--build-timeout', type=int, default=1200)
    parser.add_argument('--execute', action='store_true', help='authorize build and all replay stages')
    args = parser.parse_args(argv)
    if min(args.timeout, args.build_timeout) <= 0:
        parser.error('timeouts must be positive')
    for name in ('snapshot', 'programs', 'smokes', 'out'):
        setattr(args, name, getattr(args, name).resolve())
    for source in (HERE, args.snapshot, args.programs, args.smokes):
        if args.out == source or args.out in source.parents or source in args.out.parents:
            parser.error('output must be independent of sources, snapshot and programs')
    return args


def main():
    args = parse_args()
    # Refuse even an empty existing directory: no overwrite or implicit resume.
    args.out.mkdir(parents=True, exist_ok=False)
    status = dict(schema_version=1, status='PREPARING', created_at=now(),
                  pid=os.getpid(), jobs=args.jobs, stages=stages(args))
    path = args.out / 'status.json'
    atomic_json(path, status)
    current = None
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        pins = inputs(args)
        plan = dict(schema_version=1, inputs_sha256=pins, stages=status['stages'],
                    snapshot=str(args.snapshot), scope='bare-metal architectural ports and smoke only')
        atomic_json(args.out / 'plan.json', plan)
        status['plan_sha256'] = sha(args.out / 'plan.json')
        if not args.execute:
            status['status'] = 'PLANNED'
            return 0
        status['status'] = 'RUNNING'
        for current in status['stages']:
            verify(pins)
            if sha(args.out / 'plan.json') != status['plan_sha256']:
                raise ValueError('pipeline plan drift')
            current.update(status='RUNNING', started_at=now())
            status['current_stage'] = current['name']
            atomic_json(path, status)
            print(current['command'], flush=True)
            current['returncode'] = execute_stage(current)
            if current['returncode'] != 0:
                raise ValueError('stage exited nonzero: ' + current['name'])
            acceptance(current)
            verify(pins)
            current.update(status='PASS', completed_at=now())
            atomic_json(path, status)
        status['status'] = 'PASS'
        return 0
    except (Exception, KeyboardInterrupt) as error:
        state = 'INTERRUPTED' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'FAIL'
        status.update(status=state, error=f'{type(error).__name__}: {error}')
        if current is not None:
            current.update(status=state, completed_at=now())
        for stage in status['stages']:
            if stage['status'] == 'PENDING':
                stage['status'] = 'NOT_RUN'
        return 130 if state == 'INTERRUPTED' else 1
    finally:
        status['updated_at'] = now()
        atomic_json(path, status)
        print(f"{status['status']}: {path}", flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
