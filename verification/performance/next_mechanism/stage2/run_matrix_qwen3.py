#!/usr/bin/env python3
"""Same-image Qwen3 raw Q4_K matrix pair; independent C-ref, no GGML golden."""
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
PRIOR = OUT / 'stage2_matrix_vcs_20261109_02'
CAPTURE = OUT / 'stage2_qwen3_rows8_20261109_02'
LOCAL = ('run_matrix_qwen3.py', 'matrix_real_vectors.c', 'test_matrix_real_vectors.py')
MODEL_SHA = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'


def pair_maps(old, files):
    maps = []
    for group in (old.SLICES[:2], old.SLICES[2:]):
        merged, flags = {}, 0
        for name, start, m, col, _ in group:
            case, = old.vectors(Path(files[name]['baseline']).read_text())
            stride = 32 if m == 4 else 16
            for index, bits in case['outputs'].items():
                key = (start + index // stride, col + index % stride)
                if key in merged:
                    raise ValueError('Overlapping output slices')
                merged[key] = bits
            flags |= case['flags']
        maps.append((merged, flags))
    if maps[0] != maps[1] or set(maps[0][0]) != {(r, c) for r in range(8) for c in range(32)}:
        raise ValueError('Independent M4/M8 golden/flags mismatch')
    return dict(outputs=256, fflags=maps[0][1], bit_exact=True)


def prepare(out):
    old = checker.legacy()
    if out.parent != OUT:
        raise ValueError('Use a new direct signoff out child')
    prior = json.loads((PRIOR / 'report.json').read_text())
    if prior['state'] != 'PASS' or not prior['source_image_input_post_match']:
        raise ValueError('Prior full engine matrix gate is not PASS')
    captured = json.loads((CAPTURE / 'result.json').read_text())
    if captured['state'] != 'CAPTURED_NOT_BENCHMARKED' or not captured['source_pins_match']:
        raise ValueError('Need accepted raw capture')
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

    source_manifest = json.loads((checker.ORIGINAL / 'source-pins.json').read_text())
    # Historical frozen build inputs, not live production paths. Parent may
    # commit or subsequently change live RTL without changing these images.
    frozen = {p: h for p, h in source_manifest.items() if Path(p).is_relative_to(checker.ORIGINAL)}
    old.verify(frozen)
    pins.update(frozen)
    for path in (PRIOR / 'report.json', PRIOR / 'source-pins-after.json', checker.ORIGINAL / 'report.json',
                 checker.ORIGINAL / 'source-pins.json', CAPTURE / 'result.json', CAPTURE / 'source-pins.json'):
        pins[str(path)] = checker.sha(path)
    for name in LOCAL:
        copy(HERE / name, local / name)
    old_local = PRIOR / 'inputs' / HERE.relative_to(ROOT)
    for name in ('run_matrix.py', 'check_matrix_v2.py'):
        copy(old_local / name, local / name)
    original_inputs = checker.ORIGINAL / 'inputs'
    for rel in ('verification/qbs/qbs_command_vectors.c', 'verification/qbs/qbs_ref.c',
                'verification/qbs/qbs_ref.h', 'apps/common/qbs_abi.h'):
        copy(original_inputs / rel, snapshot / rel, source_manifest[str(original_inputs / rel)])
    images = json.loads((checker.ORIGINAL / 'report.json').read_text())['images']
    for arm, image in images.items():
        for name, digest in image.items():
            rel = Path(name).relative_to(checker.ORIGINAL / arm)
            copy(PRIOR / arm / rel, out / arm / rel, digest)
    for name in ('weight_q4_K.bin', 'activation_f32.bin'):
        copy(original_inputs / 'capture' / name, snapshot / 'prior_capture' / name)
    for name, *_ in old.SLICES:
        path = checker.ORIGINAL / f'{name}_baseline.txt'
        pins[str(path)] = checker.sha(path)
    for view, source in (('attn_q', 'attn_norm-0'), ('ffn_gate', 'ffn_norm-0')):
        metadata = json.loads((CAPTURE / view / 'operator.json').read_text())
        if metadata not in captured['views'] or metadata['captured_weight_shape'] != [2048, 128] or metadata['activation_shape'] != [2048, 8] or metadata['distinct_rows'] != 8 or metadata['model_sha256'] != MODEL_SHA or metadata['source'] != source or metadata['tensor'] != f'blk.0.{view}.weight':
            raise ValueError('Wrong real capture shape/identity')
        for name, key in (('weight_q4_K.bin', 'weight_sha256'), ('activation_f32.bin', 'activation_sha256')):
            copy(CAPTURE / view / name, snapshot / 'capture' / view / name, metadata[key])
        copy(CAPTURE / view / 'operator.json', snapshot / 'capture' / view / 'operator.json')
    cc = shutil.which('cc')
    if not cc:
        raise ValueError('Host C compiler required')
    deadline = time.monotonic() + 180
    program = out / 'matrix_real_vectors'
    old.command([cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-ffp-contract=off',
                 '-frounding-math', '-I' + str(snapshot / 'apps/common'), local / 'matrix_real_vectors.c',
                 snapshot / 'verification/qbs/qbs_ref.c', '-lm', '-o', program], out, out / 'oracle-build.log', deadline, 90)
    validation = out / 'prior_validation'
    validation.mkdir()
    for name, start, m, col, n in old.SLICES:
        old.command([program, validation / f'{name}.txt', snapshot / 'prior_capture', 1536, 1536, start, m, col, n],
                    out, validation / f'{name}.log', deadline, 30)
    vector_info, oracle = {}, {}
    for view in ('attn_q', 'ffn_gate'):
        folder = out / view
        folder.mkdir()
        vector_info[view] = {}
        for name, start, m, col, n in old.SLICES:
            baseline, candidate = folder / f'{name}_baseline.txt', folder / f'{name}_candidate.txt'
            old.command([program, baseline, snapshot / 'capture' / view, 128, 2048, start, m, col, n],
                        out, folder / f'{name}_oracle.log', deadline, 30)
            updated, changes = old.candidate_vector(baseline.read_text())
            candidate.write_text(updated)
            vector_info[view][name] = dict(baseline=str(baseline), candidate=str(candidate), changes=changes)
        oracle[view] = pair_maps(old, vector_info[view])
    old.save(out / 'oracle-pair.json', dict(views=oracle, golden='independent ordered qbs_ref',
             ggml_projection_check=False, captured_golden=None, performance_measured=False))
    old.save(out / 'selection.json', dict(local=str(local), vectors=vector_info, timeout_seconds=7200,
             prior=str(PRIOR), capture=str(CAPTURE), oracle=str(program), recompiled_rtl=False,
             golden='qbs_ref', captured_golden=None, ggml_projection_check=False, scope='engine_not_soc'))
    old.command([sys.executable, '-B', local / 'test_matrix_real_vectors.py', out], out, out / 'host-tests.log', deadline, 60)
    for path in (Path(cc).resolve(), Path(sys.executable).resolve(), *out.glob('*'),
                 *validation.glob('*'), *(out / 'attn_q').glob('*'), *(out / 'ffn_gate').glob('*')):
        if path.is_file():
            pins[str(path)] = checker.sha(path)
    old.verify(pins)
    if any(Path(p).is_relative_to(ROOT / 'hardware/src') for p in pins):
        raise ValueError('Must not pin live production RTL')
    old.save(out / 'source-pins.json', pins)
    old.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_matrix_qwen3.py'),
             source_pins_sha256=checker.sha(out / 'source-pins.json'), recompiled_rtl=False, live_production_pins=0))
    print(local / 'run_matrix_qwen3.py', flush=True)


def execute(out):
    old = checker.legacy()
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_matrix_qwen3.py':
        raise ValueError('Use frozen worker')
    pins = json.loads((out / 'source-pins.json').read_text())
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', runs={}, scope=config['scope'], ggml_projection_check=False,
                  golden='independent qbs_ref bit-exact output/flags', recompiled_rtl=False, retries=0)
    try:
        old.verify(pins)
        for view in ('attn_q', 'ffn_gate'):
            for name, *_ in old.SLICES:
                for arm, enable in (('baseline', 0), ('candidate', 1)):
                    work = out / arm
                    vector = Path(config['vectors'][view][name][arm])
                    log = work / f'{view}_{name}.log'
                    argv = [work / 'simv', '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector),
                            '+QBS_FUNCTIONAL_ONLY', '+QBS_FP_PROBE']
                    old.verify(pins)
                    old.save(work / f'{view}_{name}-command.json', list(map(str, argv)))
                    old.save(out / 'status.json', dict(state='RUNNING', view=view, slice=name, arm=arm))
                    print(f'STAGE2_QWEN3_RUNNING {view} {name} {arm}', flush=True)
                    old.command(argv, work, log, deadline, 900)
                    report['runs'][f'{view}_{name}_{arm}'] = checker.check_log(log.read_text(), old.vectors(vector.read_text()), enable, 'real')
                    old.verify(pins)
                    old.save(out / 'progress.json', report)
                    print(f'STAGE2_QWEN3_CHECKED {view} {name} {arm}', flush=True)
        report['paired_cycles'] = {view: {arm: {m: sum(report['runs'][f'{view}_{m}{half}_{arm}']['cycles'][0] for half in ('a', 'b'))
                                    for m in ('m4', 'm8')} for arm in ('baseline', 'candidate')} for view in ('attn_q', 'ffn_gate')}
        old.verify(pins)
        old.save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', source_image_data_post_match=True, live_production_pins=0,
                      performance_scope='engine command cycles only; not SoC/CPU/DDR/model speedup')
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): checker.sha(p) for p in out.rglob('*') if p.is_file() and
                           p.suffix in ('.log', '.json') and p.name not in ('report.json', 'status.json', 'service.log')}
    old.save(out / 'report.json', report)
    old.save(out / 'status.json', dict(state=report['state'], error=report.get('error'), report=str(out / 'report.json')))
    print('STAGE2_QWEN3_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
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
