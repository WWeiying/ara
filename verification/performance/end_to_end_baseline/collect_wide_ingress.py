#!/usr/bin/env python3
"""Independently replay exact compute/default/complete-controller receipts."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins
import run_wide_compute as compute
import run_wide_default_engine as default
import run_wide_complete_engine as complete

ACCEPTED = {
    'compute': ('e2e_wide_compute_20261106_01',
                '8badb69f8ca82f5a31ce0e601622a90944d5e3da9a418bc014e3dae5cfaed577',
                'WIDE_WEIGHT_COMPUTE_PAIR_PASS'),
    'default': ('e2e_wide_default_engine_20261106_01',
                'fc937bdf96d44abac0d95eb14cd1bd974775afba2ec2c3a0fe47ceaa29c82b76',
                'DEFAULT_COMPLETE_QBS_ENGINE_CYCLES_UNCHANGED'),
    'complete': ('e2e_wide_complete_engine_20261106_01',
                 'e04bd5e2a34ebdb2ba29caf6592c1d647b2cf73d02bfc9c49f373c1f1619717b',
                 'WIDE_COMPLETE_QBS_COMMAND_PAIR_PASS'),
}


def same(actual, recorded):
    require(json.loads(json.dumps(actual)) == recorded, 'Raw checker replay differs')


def load_accepted(run, expected_sha, state):
    require(digest(run / 'result.json') == expected_sha, 'Unaccepted result identity')
    value = json.loads((run / 'result.json').read_text())
    require(value['state'] == state, 'Unaccepted worker state')
    require(digest(run / 'source-pins.json') == value['source_pins_sha256'], 'Pin inventory identity')
    pins = json.loads((run / 'source-pins.json').read_text())
    return value, pins, dict(source_pins=verify_pins(pins), artifacts=verify_pins(value['artifacts']))


def run(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(default.RUNS), 'Fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}
    result = dict(state='FAIL', simulations_launched=0, production_enabled=False,
                  model_speedup_measured=False, physical_soc_accepted=False, real_pmp_accepted=False)
    try:
        for name in ('collect_wide_ingress.py', 'test_collect_wide_ingress.py', 'audit.py',
                     'run_wide_compute.py', 'run_wide_default_engine.py', 'run_wide_complete_engine.py'):
            path = default.HERE / name
            pins[str(path)] = digest(path)
        loaded, scopes = {}, {}
        for key, (name, expected, state) in ACCEPTED.items():
            path = default.RUNS / name
            value, inventory, counts = load_accepted(path, expected, state)
            for file, sha in inventory.items():
                require(file not in pins or pins[file] == sha, 'Incompatible campaign inputs')
                pins[file] = sha
            for artifact, sha in value['artifacts'].items(): pins[artifact] = sha
            pins[str(path / 'result.json')] = expected
            loaded[key] = value
            scopes[key] = dict(run=str(path), result_sha256=expected,
                               source_pins_sha256=value['source_pins_sha256'], **counts)
        r = default.RUNS / ACCEPTED['compute'][0]
        measured_compute = compute.check_pair((r / 'run-0.log').read_text(),
            (r / 'run-1.log').read_text(), (r / 'vectors-matrix1.txt').read_text())
        same(measured_compute, json.loads((r / 'measured.json').read_text()))
        vector = (default.ORIGINAL / 'matrix-base.txt').read_text()
        r = default.RUNS / ACCEPTED['default'][0]
        measured_default = default.check((r / 'functional.log').read_text(), vector,
            (default.ORIGINAL / 'run-matrix-gap0-0.log').read_text())
        same(measured_default, loaded['default']['measured'])
        r = default.RUNS / ACCEPTED['complete'][0]
        measured_complete = {f'{width}-gap{gap}': complete.check(
            (r / f'run{width}-gap{gap}.log').read_text(), vector, width, gap)
            for width in (128, 256) for gap in (0, 3)}
        same(measured_complete, loaded['complete']['measured'])
        pairs = {str(gap): complete.check_pair(measured_complete[f'128-gap{gap}'],
                                             measured_complete[f'256-gap{gap}']) for gap in (0, 3)}
        same(pairs, loaded['complete']['pairs'])
        same(measured_complete['128-gap0']['direct'], loaded['default']['measured']['direct'])
        same(measured_complete['128-gap0']['contexts'], loaded['default']['measured']['contexts'])
        verify_pins(pins)
        result.update(state='OPTIONAL_WIDE_INGRESS_COMPONENTS_REPLAYED', scopes=scopes,
            compute=dict(normal_per_image=measured_compute['normal_per_image'],
                         recovery_per_image=measured_compute['recovery_per_image'],
                         faults_per_image=measured_compute['faults_per_image'],
                         fp_event_count=measured_compute['fp_event_count'],
                         fp_sequence_operands_equal=measured_compute['fp_sequence_operands_equal']),
            default_complete_controller_cycles_unchanged=True, complete_command_pairs=pairs,
            limitations=['Component and synthetic complete-controller tests, not physical SoC or model timing',
                         'Original arithmetic in complete command pair; WideMatrixDot only compute pair',
                         'Golden/context/fault checks retained; AXI injection is first-beat-only',
                         'No real CVA6 PMP, ordinary RVV/AKV SoC or hardware PPA acceptance'])
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
