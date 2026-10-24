#!/usr/bin/env python3
"""Offline command-busy attribution for a terminal, accepted GQA6 ABBA."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import run_qk_panel4_abba as gate

TYPES = {4: 'FULL', 5: 'REFILL', 6: 'QK_COLUMN', 2: 'PV_ROW', 3: 'RELEASE'}


def analyze(text):
    checked = gate.check_log(text)
    groups, active = [], None
    for line in text.splitlines():
        if line.startswith('AKV_QK_TRIAL_BEGIN '):
            active = {name: dict(commands=0, busy_cycles=0) for name in TYPES.values()}
        elif line.startswith('[AKV_PERF] '):
            row = gate.numeric_fields(line[len('[AKV_PERF] '):], gate.PERF_FIELDS)
            gate.require(active is not None, 'Command outside trial')
            target = active[TYPES[row['command']]]
            target['commands'] += 1
            target['busy_cycles'] += row['busy_cycles']
        elif line.startswith('AKV_QK_ATTENTION '):
            trial = checked['trials'][len(groups)]
            busy = sum(x['busy_cycles'] for x in active.values())
            gate.require(busy == trial['derived_hardware_totals']['busy_cycles'],
                         'Busy grouping does not conserve raw command records')
            gate.require(sum(x['commands'] for x in active.values()) ==
                         trial['derived_hardware_totals']['records'], 'Command grouping mismatch')
            groups.append(dict(trial=trial['trial'], panel4=trial['panel4'],
                measured_cycles=trial['cycles'], command_types=active,
                engine_busy_cycles=busy, measured_minus_engine_busy=trial['cycles']-busy))
            active = None
    gate.require(len(groups) == 4 and active is None, 'Incomplete grouped work')
    totals = {}
    for mode in (0, 1):
        selected = [g for g in groups if g['panel4'] == mode]
        totals[str(mode)] = dict(
            measured_cycles=sum(g['measured_cycles'] for g in selected),
            engine_busy_cycles=sum(g['engine_busy_cycles'] for g in selected),
            measured_minus_engine_busy=sum(g['measured_minus_engine_busy'] for g in selected),
            command_types={name: {field: sum(g['command_types'][name][field] for g in selected)
                                  for field in ('commands', 'busy_cycles')}
                           for name in TYPES.values()})
        gate.require(totals[str(mode)]['measured_cycles'] == checked['sums'][str(mode)],
                     'Measured-cycle conservation')
    return dict(state='ACCEPTED_LOG_GROUPING_PASS', trials=groups, summed_modes=totals,
        attention_speedup=checked['attention_speedup'],
        cycle_reduction_percent=checked['cycle_reduction_percent'],
        limits='Command busy is not an exclusive stall or FPU utilization breakdown. '
               'Measured minus busy includes unassigned and potentially overlapping '
               'scalar/vector work, synchronization and command gaps. No model claim.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--result-sha256')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        from test_qk_panel4_abba import fixture
        text = fixture()
        result = analyze(text)
        gate.require([g['engine_busy_cycles'] for g in result['trials']] ==
                     [7740, 3900, 3900, 7740], 'Synthetic grouping failed')
        for bad in (text.replace('busy_cycles=10', 'busy_cycles=11', 1),
                    text.replace('AKV_QK_ATTENTION trial=0', 'AKV_QK_ATTENTION trial=1', 1)):
            try:
                analyze(bad)
            except ValueError:
                continue
            raise ValueError('Corrupted source evidence accepted')
        print('HOST_GROUPING_TEST_PASS mutations=2 no_simulation=1')
        return
    gate.require(args.run and args.result_sha256 and args.output, 'Require run, hash and output')
    run = args.run.resolve(strict=True)
    output = args.output.resolve()
    gate.require(not output.exists() and not output.is_relative_to(run), 'Use fresh separate output')
    saved = gate.read_json(run/'result.json')
    status = gate.read_json(run/'status.json')
    gate.require(saved['state'] == status['state'] == 'PASS' and status['child_pid'] is None,
                 'Run not terminal PASS')
    gate.require(gate.digest(run/'result.json') == args.result_sha256, 'Accepted result hash mismatch')
    pins = gate.read_json(run/'source-pins.json')
    gate.merge_pins(pins, saved['evidence_sha256'])
    gate.merge_pins(pins, gate.hashes([run/'result.json', run/'status.json', Path(__file__).resolve()]))
    gate.verify_pins(pins)
    text = (run/'work/run.vcs.log').read_text()
    parsed = gate.check_log(text)
    gate.require(all(saved[k] == v for k, v in parsed.items()), 'Saved versus raw result mismatch')
    uvm = gate.read_json(run/'work/uvm_result.json')
    gate.require(uvm['issues'] == [] and uvm['log_sha256'] == gate.digest(run/'work/run.vcs.log'),
                 'UVM evidence mismatch')
    result = analyze(text)
    gate.verify_pins(pins)
    output.mkdir(parents=True, exist_ok=False)
    (output/'pins.json').write_text(json.dumps(pins, indent=2, sort_keys=True)+'\n')
    result.update(run=str(run), accepted_result_sha256=args.result_sha256,
                  post_pins_match=True, pins_sha256=gate.digest(output/'pins.json'))
    (output/'analysis.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(result['summed_modes'], sort_keys=True))


if __name__ == '__main__':
    main()
