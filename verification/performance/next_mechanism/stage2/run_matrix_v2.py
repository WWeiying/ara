#!/usr/bin/env python3
"""Resume matrix01 after a scoped offline parser audit; reuse exact simv images."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
import check_matrix_v2 as checker

HERE = Path(__file__).resolve().parent
LOCAL = ('run_matrix_v2.py', 'check_matrix_v2.py', 'test_check_matrix_v2.py', 'run_matrix.py')


def prepare(out):
    old = checker.legacy()
    if out.parent != old.OUT:
        raise ValueError('Use a new direct signoff out child')
    audit = checker.audit_original()
    out.mkdir(exist_ok=False)
    local = out / 'inputs' / HERE.relative_to(old.ROOT)
    local.mkdir(parents=True)
    pins = json.loads((checker.ORIGINAL / 'source-pins.json').read_text())
    pins.update(audit['evidence_pins'])
    original_report = json.loads((checker.ORIGINAL / 'report.json').read_text())

    def copy(source, target, expected=None):
        digest = checker.sha(source)
        if expected is not None and digest != expected:
            raise ValueError('Image/source changed before copy: ' + str(source))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if checker.sha(target) != digest:
            raise ValueError('Copy race: ' + str(source))
        pins[str(source)] = pins[str(target)] = digest

    for name in LOCAL:
        copy(HERE / name, local / name)
    for arm, image in original_report['images'].items():
        for name, digest in image.items():
            source = Path(name)
            copy(source, out / arm / source.relative_to(checker.ORIGINAL / arm), digest)
    deadline = time.monotonic() + 120
    old.command([sys.executable, '-B', local / 'test_check_matrix_v2.py'], out, out / 'host-tests.log', deadline, 60)
    old.command([sys.executable, '-B', local / 'check_matrix_v2.py', '--output', out / 'offline-audit'],
                out, out / 'offline-audit.log', deadline, 60)
    old_config = json.loads((checker.ORIGINAL / 'selection.json').read_text())
    old.save(out / 'selection.json', dict(local=str(local), original=str(checker.ORIGINAL),
             vectors=old_config['vectors'], timeout_seconds=7200, reuse_images=True,
             scope='engine_not_soc', compiled_images_modified=False, retries=0,
             source_reference='pinned raw RTL; baseline CooperativeWaves=0, candidate=1; no git HEAD reference',
             continuation=[['context', 'candidate', 1]] +
                [[name, arm, enable] for name, *_ in old.SLICES for arm, enable in (('baseline', 0), ('candidate', 1))]))
    for path in (out / 'selection.json', out / 'host-tests.log', out / 'offline-audit.log',
                 out / 'offline-audit/report.json', Path(sys.executable).resolve()):
        pins[str(path)] = checker.sha(path)
    old.verify(pins)
    old.save(out / 'source-pins.json', pins)
    old.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_matrix_v2.py'),
             old_worker_state='FAIL_PRESERVED', offline_audit='OFFLINE_RECHECK_PASS_PARTIAL',
             source_pins_sha256=checker.sha(out / 'source-pins.json'), recompiled=False))
    print(local / 'run_matrix_v2.py', flush=True)


def execute(out):
    old = checker.legacy()
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_matrix_v2.py':
        raise ValueError('Use the frozen successor worker')
    pins = json.loads((out / 'source-pins.json').read_text())
    audit = json.loads((out / 'offline-audit/report.json').read_text())
    if audit['state'] != 'OFFLINE_RECHECK_PASS_PARTIAL' or audit['original_worker_state'] != 'FAIL':
        raise ValueError('Missing scoped offline audit')
    report = dict(state='FAIL', original_worker_state='FAIL_PRESERVED', recompiled=False,
                  offline_audit_sha256=checker.sha(out / 'offline-audit/report.json'),
                  scope=config['scope'], runs=dict(audit['runs']), retries=0)
    deadline = time.monotonic() + config['timeout_seconds']
    try:
        old.verify(pins)
        checker.audit_original()
        for suite, arm, enable in config['continuation']:
            work = out / arm
            vector = Path(config['vectors'][suite][arm])
            argv = [work / 'simv', '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector),
                    '+QBS_FUNCTIONAL_ONLY', '+QBS_FP_PROBE']
            if suite == 'context':
                argv += ['+QBS_CONTEXT_SUITE']
            old.verify(pins)
            old.save(work / f'{suite}-command.json', list(map(str, argv)))
            old.save(out / 'status.json', dict(state='RUNNING', phase=suite, arm=arm, recompiled=False))
            print(f'STAGE2_MATRIX_V2_RUNNING {suite} {arm}', flush=True)
            old.command(argv, work, work / f'{suite}.log', deadline, 900)
            result = checker.check_log((work / f'{suite}.log').read_text(), old.vectors(vector.read_text()), enable, suite)
            old.verify(pins)
            report['runs'][f'{suite}_{arm}'] = result
            old.save(out / 'progress.json', report)
            print(f'STAGE2_MATRIX_V2_CHECKED {suite} {arm}', flush=True)
        report['paired_cycles'] = {arm: {m: sum(report['runs'][f'{m}{half}_{arm}']['cycles'][0] for half in ('a', 'b'))
                                         for m in ('m4', 'm8')} for arm in ('baseline', 'candidate')}
        old.verify(pins)
        checker.audit_original()
        old.save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', source_image_input_post_match=True, original_report_preserved=True,
                      numerical='original qbs_ref bit-exact golden/flags and original canonical SV checker unchanged',
                      performance_scope='engine command cycles only; no SoC/CPU/DDR/model speedup claim')
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): checker.sha(p) for p in out.rglob('*') if p.is_file() and
                           p.suffix in ('.log', '.json') and p.name not in ('report.json', 'status.json', 'service.log')}
    old.save(out / 'report.json', report)
    old.save(out / 'status.json', dict(state=report['state'], error=report.get('error'), report=str(out / 'report.json')))
    print('STAGE2_MATRIX_V2_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
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
