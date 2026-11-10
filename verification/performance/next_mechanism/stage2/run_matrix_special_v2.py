#!/usr/bin/env python3
"""ISA canonical-NaN adapter for final O records; reuse sealed queue images."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
import check_matrix_v2 as checker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = checker.ORIGINAL.parent
RAW = OUT / 'stage2_matrix_special_vcs_20261109_01'
QUEUE = OUT / 'stage2_matrix_queue_vcs_20261109_01'
RAW_SHA = '8d324162e0f80ee863feb08f0b2976026cdce430a6886c9c85764edc026cff97'
RAW_LOG_SHA = 'ecff35b276849fde2ceaf6537bc4541856ee50f9d58e265fc07a9644e91c11d2'
LOCAL = ('run_matrix_special_v2.py', 'test_matrix_special_v2.py')
ISA_URL = 'https://docs.riscv.org/reference/isa/v20260120/unpriv/f-st-ext.html#_nan_generation_and_propagation'


def is_nan(bits):
    return bits & 0x7f800000 == 0x7f800000 and bits & 0x007fffff != 0


def canonicalize(text):
    checker.legacy().vectors(text)
    result, changes, case = [], [], None
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        if line.startswith('CMD '):
            case = int(line.split()[1])
        if line.startswith('O '):
            match = re.fullmatch(r'(O ([0-9]+) )([0-9a-f]{8})(\n?)', line)
            if not match:
                raise ValueError('Unexpected O serialization')
            bits = int(match[3], 16)
            if is_nan(bits) and bits != 0x7fc00000:
                changes.append(dict(line=number, case=case, index=int(match[2]),
                                    before=match[3], after='7fc00000'))
                line = match[1] + '7fc00000' + match[4]
        result.append(line)
    return ''.join(result), changes


def validate_adaptation(raw, runtime):
    canonical, changes = canonicalize(raw)
    expected, dot_changes = checker.legacy().candidate_vector(canonical)
    if runtime != expected:
        raise ValueError('Outside allowed final-NaN/dot expectation adaptation')
    old_cases = checker.legacy().vectors(raw)
    new_cases = checker.legacy().vectors(runtime)
    for old, new in zip(old_cases, new_cases):
        if old['flags'] != new['flags']:
            raise ValueError('Flags changed')
        for index, bits in old['outputs'].items():
            if new['outputs'][index] != (0x7fc00000 if is_nan(bits) else bits):
                raise ValueError('Non-NaN changed or NaN not canonical')
    return changes, dot_changes


def prepare(out):
    old = checker.legacy()
    if out.parent != OUT:
        raise ValueError('Use a new direct signoff out child')
    accepted = json.loads((QUEUE / 'report.json').read_text())
    if accepted['state'] != 'PASS' or not accepted['source_image_post_match']:
        raise ValueError('Sealed queue gate not PASS')
    if checker.sha(RAW / 'original_vectors.txt') != RAW_SHA or checker.sha(RAW / 'host-tests.log') != RAW_LOG_SHA:
        raise ValueError('Original raw failure evidence changed')
    out.mkdir(exist_ok=False)
    snapshot, pins = out / 'inputs', {}
    local = snapshot / HERE.relative_to(ROOT)

    def copy(source, target, expected=None):
        digest = checker.sha(source)
        if expected is not None and digest != expected:
            raise ValueError('Sealed input drift: ' + str(source))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if checker.sha(target) != digest:
            raise ValueError('Copy race: ' + str(source))
        pins[str(source)] = pins[str(target)] = digest

    original_pins = json.loads((QUEUE / 'source-pins.json').read_text())
    frozen = {p: h for p, h in original_pins.items() if Path(p).is_relative_to(QUEUE)}
    old.verify(frozen)
    pins.update(frozen)
    for path in (QUEUE / 'report.json', QUEUE / 'source-pins.json', QUEUE / 'source-pins-after.json'):
        pins[str(path)] = checker.sha(path)
    for name in LOCAL:
        copy(HERE / name, local / name)
    previous_local = QUEUE / 'inputs' / HERE.relative_to(ROOT)
    for name in ('run_matrix.py', 'check_matrix_v2.py', 'run_matrix_queue.py'):
        copy(previous_local / name, local / name)
    for source in sorted((RAW / 'inputs').rglob('*')):
        if source.is_file():
            copy(source, snapshot / 'raw_producer' / source.relative_to(RAW / 'inputs'))
    for name in ('original_vectors.txt', 'vectors.txt', 'oracle.log', 'oracle-build.log',
                 'host-tests.log', 'selection.json', 'preflight-report.json', 'matrix_special_vectors'):
        copy(RAW / name, out / 'raw_evidence' / name)
    for depth, image in accepted['images'].items():
        for source, digest in image.items():
            copy(Path(source), out / f'q{depth}' / Path(source).relative_to(QUEUE / f'q{depth}'), digest)
    raw = (out / 'raw_evidence/original_vectors.txt').read_text()
    canonical, changes = canonicalize(raw)
    (out / 'canonical_vectors.txt').write_text(canonical)
    runtime, dot_changes = old.candidate_vector(canonical)
    validate_adaptation(raw, runtime)
    (out / 'vectors.txt').write_text(runtime)
    old.save(out / 'nan-differences.json', dict(policy='ISA canonical-NaN adapter; final O records only',
             isa_url=ISA_URL, original_flags_unchanged=True, non_nan_bits_unchanged=True,
             raw_sha256=checker.sha(out / 'raw_evidence/original_vectors.txt'),
             canonical_sha256=checker.sha(out / 'canonical_vectors.txt'),
             runtime_sha256=checker.sha(out / 'vectors.txt'), changes=changes, dot_changes=dot_changes))
    old.save(out / 'selection.json', dict(local=str(local), vector=str(out / 'vectors.txt'), depths=[0, 16],
             timeout_seconds=1800, recompiled_rtl=False, isa_url=ISA_URL,
             policy='ISA canonical-NaN adapter, not an RTL or flags change',
             half_snan_nv_independently_verified=False, original_failure_preserved=str(RAW)))
    deadline = time.monotonic() + 120
    old.command([sys.executable, '-B', local / 'test_matrix_special_v2.py', '--prepared', out],
                out, out / 'host-tests.log', deadline, 60)
    for path in (Path(sys.executable).resolve(), *out.glob('*')):
        if path.is_file():
            pins[str(path)] = checker.sha(path)
    old.verify(pins)
    old.save(out / 'source-pins.json', pins)
    old.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_matrix_special_v2.py'),
             source_pins_sha256=checker.sha(out / 'source-pins.json'), nan_output_changes=len(changes),
             recompiled_rtl=False, production_files_changed=False))
    print(local / 'run_matrix_special_v2.py', flush=True)


def execute(out):
    old = checker.legacy()
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_matrix_special_v2.py':
        raise ValueError('Use frozen worker')
    pins = json.loads((out / 'source-pins.json').read_text())
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', runs={}, recompiled_rtl=False, retries=0, scope='engine_not_soc',
                  policy=config['policy'], half_snan_nv_independently_verified=False)
    try:
        old.verify(pins)
        vector = Path(config['vector'])
        validate_adaptation((out / 'raw_evidence/original_vectors.txt').read_text(), vector.read_text())
        import run_matrix_queue
        for depth in config['depths']:
            work = out / f'q{depth}'
            argv = [work / 'simv', '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector), '+QBS_FUNCTIONAL_ONLY', '+QBS_FP_PROBE']
            old.save(work / 'command.json', list(map(str, argv)))
            old.save(out / 'status.json', dict(state='RUNNING', depth=depth))
            print(f'STAGE2_SPECIAL_V2_RUNNING depth={depth}', flush=True)
            old.command(argv, work, work / 'run.log', deadline, 600)
            text = (work / 'run.log').read_text()
            result = checker.check_log(text, old.vectors(vector.read_text()), 1, 'special')
            result['queue'] = run_matrix_queue.check_queue_log(text, depth)
            report['runs'][str(depth)] = result
            old.verify(pins)
            print(f'STAGE2_SPECIAL_V2_CHECKED depth={depth}', flush=True)
        old.save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', source_image_post_match=True, original_failure_preserved=True,
                      nan_output_changes=88, scenarios_per_image=6)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): checker.sha(p) for p in out.rglob('*') if p.is_file() and
                           p.suffix in ('.log', '.json', '.txt') and p.name not in ('report.json', 'status.json', 'service.log')}
    old.save(out / 'report.json', report)
    old.save(out / 'status.json', dict(state=report['state'], error=report.get('error'), report=str(out / 'report.json')))
    print('STAGE2_SPECIAL_V2_' + report['state'], flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        raise SystemExit(execute(args.output.resolve()))
    prepare(args.output.resolve())
