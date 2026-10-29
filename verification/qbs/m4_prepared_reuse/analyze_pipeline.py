#!/usr/bin/env python3
"""Audit QBS activity in the accepted M4 Q/K/V ABBA, without a new simulation."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PHASES = tuple('phase_'+name+'_cycles' for name in
    ('setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
     'scheduler', 'commit', 'fault', 'terminal'))
PROBES = ('probe_compute_without_dot_issue_cycles', 'probe_context_start_blocked_cycles',
    'probe_profile_result_blocked_cycles', 'probe_fp_slot_blocked_cycles',
    'probe_fp_accumulator_blocked_cycles', 'probe_fp_other_blocked_cycles',
    'probe_fp_input_blocked_cycles', 'probe_fp_no_schedulable_uop_cycles',
    'probe_profile_correction_pending_cycles', 'probe_profile_result_pending_cycles')
COUNTS = ('busy_cycles', 'tiles', 'useful_pairs', 'pair_capacity', 'dot_active_cycles',
          'fp_uop_issue', 'weight_prefetch_wait_cycles', *PHASES, *PROBES)
RTL = tuple(ROOT/'hardware/src/vlsu/qbs'/name for name in
    ('qbs_engine.sv', 'qbs_compute_engine.sv', 'qbs_profile_engine_int.sv',
     'qbs_dot_array.sv', 'qbs_fp_accumulator.sv'))


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def fields(line, prefix):
    result = {}
    for item in line.removeprefix(prefix).split():
        key, value = item.split('=', 1)
        if key in result or not value.isdecimal():
            raise ValueError('Invalid or duplicate field: '+key)
        result[key] = int(value)
    return result


def analyze(text, accepted_trials):
    trials, pending, sequence, completed = [], [], 0, 0
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            p = fields(line, '[QBS_PERF] ')
            sequence += 1
            if completed or p['seq'] != sequence or (p['m'], p['n'], p['vlen'], p['lanes']) != (4,32,1024,4):
                raise ValueError('Unexpected command sequence/shape')
            if (p['success'], p['fault'], p['validation_fault'], p['read_fault']) != (1,0,0,0):
                raise ValueError('Failed command')
            if sum(p[k] for k in PHASES) != p['busy_cycles']:
                raise ValueError('Exclusive phases do not sum to busy cycles')
            if not 0 < p['dot_active_cycles'] <= p['busy_cycles']:
                raise ValueError('Invalid dot issue count')
            if not 0 < p['useful_pairs'] <= p['pair_capacity']:
                raise ValueError('Invalid pair count')
            if p['pair_capacity'] != 32*p['dot_active_cycles']:
                raise ValueError('Unexpected full-row issue capacity')
            if (p['probe_fp_slot_blocked_cycles'] + p['probe_fp_accumulator_blocked_cycles'] +
                    p['probe_fp_other_blocked_cycles']) != p['probe_profile_result_blocked_cycles']:
                raise ValueError('Result-blocking partition')
            for key in COUNTS:
                if key not in p:
                    raise ValueError('Missing counter: '+key)
            pending.append(p)
        elif line.startswith('M4_QKV_TRIAL '):
            t = fields(line, 'M4_QKV_TRIAL ')
            i = len(trials)
            if completed or i >= 4 or t != accepted_trials[i] or len(pending) != 64:
                raise ValueError('Trial differs from accepted numeric evidence')
            if t['id'] != i or t['reuse'] != (0,1,1,0)[i] or t['errors']:
                raise ValueError('Trial order/status')
            totals = {k:sum(p[k] for p in pending) for k in COUNTS}
            if totals['busy_cycles'] > t['execute'] or t['execute'] > t['total']:
                raise ValueError('Inconsistent activity/timing scope')
            trials.append(dict(trial=t, commands=64, counts=totals,
                dot_issue_fraction_of_busy=totals['dot_active_cycles']/totals['busy_cycles'],
                issued_pair_fill=totals['useful_pairs']/totals['pair_capacity'],
                compute_no_issue_cycles_per_tile=totals['probe_compute_without_dot_issue_cycles']/totals['tiles']))
            pending = []
        elif line.startswith('M4_QKV_RESULT '):
            if pending or len(trials) != 4 or completed or line != 'M4_QKV_RESULT errors=0 trials=4 m=4 k=1536 outputs=8192 commands=256':
                raise ValueError('Incomplete or ambiguous completion')
            completed += 1
    if pending or len(trials) != 4 or completed != 1:
        raise ValueError('Incomplete paired log')
    selected = trials[1:3]
    total = sum(t['trial']['total'] for t in selected)
    busy = sum(t['counts']['busy_cycles'] for t in selected)
    dot = sum(t['counts']['dot_active_cycles'] for t in selected)
    no_issue = sum(t['counts']['probe_compute_without_dot_issue_cycles'] for t in selected)
    return dict(trials=trials, optimized_pair=dict(total=total, busy=busy, dot_issue=dot,
        compute_no_issue=no_issue,
        idealized_all_non_dot_removed_speedup=total/(total-(busy-dot)),
        idealized_compute_no_issue_removed_speedup=total/(total-no_issue)),
        interpretation='Conditional same-work estimates only; not measured speedups or functional-unit utilization. Pending counters overlap work and are not stall cycles.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(strict=True), args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Fresh independent output required')
    receipt = json.loads((run/'result.json').read_text())
    uvm = json.loads((run/'work/uvm_result.json').read_text())
    log = run/'work/run.vcs.log'
    pins_path = run/'source-pins.json'
    if (receipt['state'] != 'PASS' or receipt['post_pins_match'] is not True or
            receipt['performance_measured'] is not True or uvm['status'] != 'PASS' or
            uvm['issues'] or uvm['elf_sha256'] != receipt['elf_sha256'] or
            uvm['log_sha256'] != digest(log) or
            digest(pins_path) != receipt['source_pins_sha256']):
        raise ValueError('Original evidence identity/status')
    original_pins = json.loads(pins_path.read_text())
    for path in RTL:
        if original_pins.get(str(path)) != digest(path):
            raise ValueError('RTL differs from measured version: '+str(path))
    result = analyze(log.read_text(), receipt['measured']['trials'])
    result.update(state='ANALYSIS_COMPLETE', new_simulations=0,
                  measured_run=str(run), current_counter_rtl_matches=True,
                  source_pins={str(p):digest(p) for p in
                    (Path(__file__), run/'result.json', run/'work/uvm_result.json', log, pins_path, *RTL)})
    out.mkdir(parents=True)
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['optimized_pair'], indent=2))


if __name__ == '__main__':
    main()
