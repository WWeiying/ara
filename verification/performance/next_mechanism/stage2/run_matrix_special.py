#!/usr/bin/env python3
"""Six raw-C-ref special-scale cases, same sealed queue images; no RTL compile."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
import check_matrix_v2 as checker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = checker.ORIGINAL.parent
QUEUE = OUT / 'stage2_matrix_queue_vcs_20261109_01'
LOCAL = ('matrix_special_vectors.c', 'run_matrix_special.py', 'test_matrix_special.py')


def prepare(out):
    old = checker.legacy()
    if out.parent != OUT:
        raise ValueError('Use a new direct signoff out child')
    accepted = json.loads((QUEUE / 'report.json').read_text())
    if accepted['state'] != 'PASS' or not accepted['source_image_post_match']:
        raise ValueError('Queue gate not PASS')
    out.mkdir(exist_ok=False)
    snapshot, pins = out / 'inputs', {}
    local = snapshot / HERE.relative_to(ROOT)

    def copy(source, target, expected=None):
        digest = checker.sha(source)
        if expected is not None and digest != expected:
            raise ValueError('Sealed identity drift: ' + str(source))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if checker.sha(target) != digest:
            raise ValueError('Copy race: ' + str(source))
        pins[str(source)] = pins[str(target)] = digest

    original_pins = json.loads((QUEUE / 'source-pins.json').read_text())
    frozen = {p: h for p, h in original_pins.items() if Path(p).is_relative_to(QUEUE)}
    old.verify(frozen)
    pins.update(frozen)
    for source in (QUEUE / 'report.json', QUEUE / 'source-pins.json', QUEUE / 'source-pins-after.json'):
        pins[str(source)] = checker.sha(source)
    for name in LOCAL:
        copy(HERE / name, local / name)
    previous_local = QUEUE / 'inputs' / HERE.relative_to(ROOT)
    for name in ('run_matrix.py', 'check_matrix_v2.py', 'run_matrix_queue.py'):
        copy(previous_local / name, local / name)
    for rel in ('verification/qbs/qbs_command_vectors.c', 'verification/qbs/qbs_ref.c',
                'verification/qbs/qbs_ref.h', 'apps/common/qbs_abi.h'):
        copy(QUEUE / 'inputs' / rel, snapshot / rel)
    for depth, image in accepted['images'].items():
        for source, digest in image.items():
            copy(Path(source), out / f'q{depth}' / Path(source).relative_to(QUEUE / f'q{depth}'), digest)
    cc = shutil.which('cc')
    if not cc:
        raise ValueError('Host C compiler required')
    deadline = time.monotonic() + 180
    program = out / 'matrix_special_vectors'
    old.command([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-ffp-contract=off', '-frounding-math',
                 '-I' + str(snapshot / 'apps/common'), local / 'matrix_special_vectors.c',
                 snapshot / 'verification/qbs/qbs_ref.c', '-lm', '-o', program], out, out / 'oracle-build.log', deadline)
    raw = out / 'original_vectors.txt'
    old.command([program, raw], out, out / 'oracle.log', deadline)
    updated, changes = old.candidate_vector(raw.read_text())
    (out / 'vectors.txt').write_text(updated)
    cases = old.vectors(updated)
    noncanonical = [dict(case=c['id'], index=i, bits=f'{bits:08x}') for c in cases for i, bits in c['outputs'].items()
                    if bits & 0x7f800000 == 0x7f800000 and bits & 0x007fffff and bits != 0x7fc00000]
    old.save(out / 'selection.json', dict(local=str(local), vector=str(out / 'vectors.txt'), timeout_seconds=1800,
             image_origin=str(QUEUE), depths=[0, 16], numerical_policy='unmodified original qbs_ref bit patterns/flags',
             noncanonical_nan_outputs=noncanonical, changes=changes, recompiled_rtl=False))
    old.command([sys.executable, '-B', local / 'test_matrix_special.py', '--prepared', out],
                out, out / 'host-tests.log', deadline, 60)
    for path in (Path(cc).resolve(), Path(sys.executable).resolve(), *out.glob('*')):
        if path.is_file():
            pins[str(path)] = checker.sha(path)
    old.verify(pins)
    old.save(out / 'source-pins.json', pins)
    old.save(out / 'prepared.json', dict(state='RAW_ORACLE_CONTRACT_BLOCKER' if noncanonical else 'PREPARED_NOT_EXECUTED',
             frozen_runner=str(local / 'run_matrix_special.py'), noncanonical_nan_outputs=len(noncanonical),
             source_pins_sha256=checker.sha(out / 'source-pins.json'), recompiled_rtl=False, simulator_launched=False))
    print(json.dumps(dict(noncanonical_nan_outputs=len(noncanonical), frozen_runner=str(local / 'run_matrix_special.py'))), flush=True)


def execute(out):
    old = checker.legacy()
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_matrix_special.py':
        raise ValueError('Use frozen worker')
    if config['noncanonical_nan_outputs']:
        raise ValueError('Original host C-ref NaN payload/sign differs from RISC-V canonical NaN; no simulator launch')
    pins = json.loads((out / 'source-pins.json').read_text())
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', runs={}, recompiled_rtl=False, retries=0, scope='engine_not_soc')
    try:
        old.verify(pins)
        vector = Path(config['vector'])
        for depth in config['depths']:
            work = out / f'q{depth}'
            argv = [work / 'simv', '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector), '+QBS_FUNCTIONAL_ONLY', '+QBS_FP_PROBE']
            old.save(work / 'command.json', list(map(str, argv)))
            old.save(out / 'status.json', dict(state='RUNNING', depth=depth))
            print(f'STAGE2_SPECIAL_RUNNING depth={depth}', flush=True)
            old.command(argv, work, work / 'run.log', deadline, 600)
            text = (work / 'run.log').read_text()
            result = checker.check_log(text, old.vectors(vector.read_text()), 1, 'special')
            import run_matrix_queue
            result['queue'] = run_matrix_queue.check_queue_log(text, depth)
            report['runs'][str(depth)] = result
            old.verify(pins)
        old.save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', source_image_post_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    old.save(out / 'report.json', report)
    old.save(out / 'status.json', dict(state=report['state'], error=report.get('error')))
    print('STAGE2_SPECIAL_' + report['state'], flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        raise SystemExit(execute(args.output.resolve()))
    prepare(args.output.resolve())
