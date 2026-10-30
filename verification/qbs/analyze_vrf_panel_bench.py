#!/usr/bin/env python3
"""Offline, fixture-specific attribution of the completed Q6_K M4/N64/K8960 ABBA."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re


PHASES = 'setup activation weight compute overlap drain scheduler commit fault terminal'.split()
PERF_FIELDS = set(('''seq id m n vlen lanes success fault validation_fault validation_error
read_fault busy_cycles read_ranges translations ar r_beats payload_bytes store_wait_cycles
read_backpressure_cycles read_outstanding_occ_sum read_outstanding_max read_outstanding_full_cycles
weight_prefetch_wait_cycles tiles weight_bytes activation_bytes useful_pairs pair_capacity
dot_active_cycles fp_uop_issue fp_table_occ_sum fp_table_occ_max fp_table_full_cycles
accumulator_updates commit_groups commit_backpressure_cycles activation_access context_fill_count
context_reuse_count context_reuse_block_count context_read_bytes activation_axi_bytes_saved
context_replay_cycles context_replay_compute_overlap_cycles context_validation_fault_count
probe_context_start_blocked_cycles probe_compute_without_dot_issue_cycles
probe_profile_result_blocked_cycles probe_fp_slot_blocked_cycles probe_fp_accumulator_blocked_cycles
probe_fp_other_blocked_cycles probe_fp_input_blocked_cycles probe_fp_no_schedulable_uop_cycles
probe_fp_busy_cycles probe_profile_context_occ_sum probe_profile_two_context_cycles
probe_profile_drain_only_cycles probe_profile_correction_pending_cycles probe_profile_result_pending_cycles
probe_read_range_blocked_cycles probe_read_range_fifo_blocked_cycles probe_read_ar_slot_blocked_cycles
probe_read_ar_ready_blocked_cycles probe_read_response_idle_cycles probe_read_data_sink_blocked_cycles
probe_read_completion_blocked_cycles probe_read_translation_wait_cycles
probe_weight_wait_no_outstanding_cycles probe_weight_wait_response_idle_cycles
probe_weight_wait_r_transfer_cycles probe_weight_wait_r_blocked_cycles''').split()) | {
    f'phase_{p}_cycles' for p in PHASES}
TOTAL_FIELDS = set('activation_axi_bytes_saved ar busy_cycles commit_groups context_fill_count '
                   'context_reuse_count payload_bytes r_beats read_ranges weight_bytes'.split())
TRIAL = re.compile(r'VRF_PANEL_TRIAL trial=([0-3]) path=(direct|striped) cycles=([1-9][0-9]*) '
                   r'flags=([0-9]+) checksum=([0-9a-f]{16})')
SUMMARY = ('VRF_PANEL_RESULT errors=0 m=4 n=64 k=8960 outputs=256 calls=4 commands=40 '
           'preparation_timed=0 descriptor_setup_timed=1')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), label + ': fields')


def pairs(items):
    result = {}
    for k, v in items:
        require(k not in result, 'duplicate field: ' + k)
        result[k] = v
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def check_pins(pins):
    for name, expected in pins.items():
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected),
                'invalid hash: ' + name)
        require(digest(name) == expected, 'pin drift: ' + name)


def analyze(log, receipt):
    keys(receipt, 'cycle_reduction_percent evidence_sha256 matrix_speedup scope state sums '
         'trials vector_traffic'.split(), 'receipt')
    require(receipt['state'] == 'PASS', 'receipt not completed PASS')
    require(receipt['vector_traffic'] == dict(commands=40, result_bytes=20480,
            seed_bytes=16384, seeded_commands=32), 'vector accounting')
    rows, markers, summaries = [], [], []
    for line in log.splitlines():
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            require(line.startswith('[QBS_PERF] '), 'malformed PERF marker')
            tokens = line[len('[QBS_PERF] '):].split(' ')
            require(all(re.fullmatch(r'[a-z_]+=[0-9]+', t) for t in tokens), 'PERF token')
            row = pairs((k, int(v)) for k, v in (t.split('=') for t in tokens))
            keys(row, PERF_FIELDS, 'PERF')
            rows.append(row)
        elif 'VRF_PANEL_TRIAL' in line:
            m = TRIAL.fullmatch(line)
            require(m is not None, 'malformed trial marker')
            markers.append(dict(trial=int(m[1]), path=m[2], cycles=int(m[3]),
                                flags=int(m[4]), checksum=m[5]))
        elif 'VRF_PANEL_RESULT' in line:
            require(line == SUMMARY, 'malformed result marker')
            summaries.append(line)
    require(len(rows) == 40 and [r['seq'] for r in rows] == list(range(1, 41)), '40 ordered commands')
    require(len(markers) == 4 and len(summaries) == 1, 'marker counts')
    require(isinstance(receipt['trials'], list) and len(receipt['trials']) == 4, 'receipt trials')
    groups = [rows[:2], rows[2:20], rows[20:38], rows[38:]]
    trials = []
    for i, (group, marker, recorded) in enumerate(zip(groups, markers, receipt['trials'])):
        path = ['direct', 'striped', 'striped', 'direct'][i]
        keys(recorded, set(marker) | {'hardware_totals'}, 'receipt trial')
        require(marker == {k: recorded[k] for k in marker}, 'trial vs receipt')
        require(marker['trial'] == i and marker['path'] == path and marker['flags'] == 1 and
                marker['checksum'] == '90924b7e574c4d19', 'ABBA/output/flags')
        for j, r in enumerate(group):
            k = 35 if path == 'direct' else (4 if j < 16 else 3)
            access = 0 if path == 'direct' else (1 if j % 2 == 0 else (3 if j == 17 else 2))
            reuse = access in (2, 3)
            expected = dict(m=4, n=32, lanes=4, vlen=1024, success=1, fault=0,
                validation_fault=0, validation_error=0, read_fault=0, translations=0,
                context_validation_fault_count=0, activation_access=access,
                tiles=8*k, weight_bytes=32*210*k, activation_bytes=4*292*k,
                useful_pairs=4*32*256*k, pair_capacity=4*32*256*k,
                dot_active_cycles=1024*k, fp_uop_issue=384*k, accumulator_updates=128*k,
                commit_groups=16, read_ranges=1+8*k+(0 if reuse else k),
                payload_bytes=16+32*210*k+(0 if reuse else 4*292*k),
                r_beats=1+424*k+(0 if reuse else 73*k),
                context_fill_count=int(access == 1), context_reuse_count=int(reuse),
                context_reuse_block_count=k if reuse else 0,
                context_read_bytes=1168*k if reuse else 0,
                activation_axi_bytes_saved=1168*k if reuse else 0,
                context_replay_compute_overlap_cycles=0, phase_fault_cycles=0)
            require(all(r[f] == v for f, v in expected.items()), f'command {r["seq"]}: geometry/work/access')
            require(sum(r[f'phase_{p}_cycles'] for p in PHASES) == r['busy_cycles'], 'phase conservation')
            require(r['phase_compute_cycles'] + r['phase_overlap_cycles'] == 1072*k, 'compute order/work budget')
            if reuse:
                require(r['context_replay_cycles'] == 74*k and r['phase_activation_cycles'] == 76*k,
                        'replay bound assumptions changed')
            else:
                require(r['context_replay_cycles'] == 0, 'unexpected replay')
        totals = {f: sum(r[f] for r in group) for f in TOTAL_FIELDS}
        keys(recorded['hardware_totals'], TOTAL_FIELDS, 'receipt totals')
        require(totals == recorded['hardware_totals'], 'hardware totals vs receipt')
        phase = {p: sum(r[f'phase_{p}_cycles'] for r in group) for p in PHASES}
        require(phase['compute'] + phase['overlap'] == 75040, 'equal trial compute work')
        residual = marker['cycles'] - totals['busy_cycles']
        require(residual >= 0, 'negative measured-minus-busy residual')
        trials.append({**marker, 'engine_busy': totals['busy_cycles'], 'phases': phase,
                       'measured_minus_engine_busy': residual, 'commands': len(group),
                       'hardware_totals': totals,
                       'context_replay_cycles': sum(r['context_replay_cycles'] for r in group),
                       'context_replay_compute_overlap_cycles': 0})
    sums = {path: sum(t['cycles'] for t in trials if t['path'] == path) for path in ('direct', 'striped')}
    require(receipt['sums'] == sums, 'cycle sums')
    require(math.isclose(receipt['matrix_speedup'], sums['direct']/sums['striped'], rel_tol=1e-12), 'speedup')
    reduction = 100*(sums['direct']-sums['striped'])/sums['direct']
    require(math.isclose(receipt['cycle_reduction_percent'], reduction, abs_tol=1e-10), 'percent')
    require(reduction < 0, 'not the archived negative result')
    return dict(correctness_receipt='PASS', performance='REGRESSION', trials=trials,
        measured_cycle_sums=sums, slowdown_percent=-reduction,
        average_loss_cycles_per_call=(sums['striped']-sums['direct'])/2,
        reuse_only_internal_activation_budget_upper_bound=26*76,
        reuse_bound_caveat='26 noninitial K blocks x 76 activation-phase cycles; assumes no displaced stalls. Not a predicted speedup.',
        decision='Keep experimental QBACC OFF; no GGML deployment. No blind lookahead enable.',
        residual_caveat='Includes descriptor construction, preflight, issue gaps, final stores and drains; aggregate counters do not isolate their individual costs.',
        scope=receipt['scope'])


def mutation_tests(log, receipt):
    first = next(line for line in log.splitlines() if line.startswith('[QBS_PERF] '))
    mutations = [log.replace(first, '', 1), log + '\n' + first,
        log.replace('[QBS_PERF]', '[QBS_PERF]_BOGUS', 1),
        log.replace(first, first + ' unknown=1', 1),
        log.replace(first, first + ' m=4', 1),
        log.replace(first, first.replace(' m=4', ''), 1),
        log.replace('VRF_PANEL_RESULT ', 'VRF_PANEL_RESULT_BOGUS ', 1),
        log.replace('VRF_PANEL_TRIAL ', 'VRF_PANEL_TRIAL_BOGUS ', 1),
        log + '\n' + SUMMARY,
        log.replace('checksum=90924b7e574c4d19', 'checksum=0000000000000000', 1)]
    for field in ['seq', 'm', 'n', 'tiles', 'activation_access', 'weight_bytes', 'activation_bytes',
                  'payload_bytes', 'useful_pairs', 'dot_active_cycles', 'fp_uop_issue',
                  'accumulator_updates', 'busy_cycles', 'phase_scheduler_cycles',
                  'phase_compute_cycles', 'context_replay_compute_overlap_cycles']:
        changed = re.sub(r'\b'+field+r'=([0-9]+)', lambda m: field+'='+str(int(m[1])+1), first)
        mutations.append(log.replace(first, changed, 1))
    cases = [(text, receipt) for text in mutations]
    for field, value in [('state', 'RUNNING'), ('matrix_speedup', float('nan')),
                         ('sums', {'direct': 1, 'striped': 2}), ('trials', [])]:
        changed = copy.deepcopy(receipt)
        changed[field] = value
        cases.append((log, changed))
    changed = copy.deepcopy(receipt)
    changed['trials'][0]['hardware_totals']['busy_cycles'] += 1
    cases.append((log, changed))
    for text, data in cases:
        try:
            analyze(text, data)
        except (ValueError, TypeError):
            continue
        raise ValueError('mutation unexpectedly accepted')
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--image-pins', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'output must be fresh')
    run = args.run.resolve()
    receipt_path, log_path = run/'result.json', run/'work/run.vcs.log'
    receipt = read_json(receipt_path)
    pins_path = run/'source-pins.json'
    pins = read_json(pins_path)
    evidence = receipt['evidence_sha256']
    require(str(log_path) in evidence and str(pins_path) in evidence, 'missing log/source pins evidence')
    root = Path(__file__).resolve().parents[2]
    image_pins = read_json(args.image_pins)
    rtl = {str(root/'hardware/src/vlsu/qbs'/name): image_pins[str(root/'hardware/src/vlsu/qbs'/name)]
           for name in ['qbs_engine.sv', 'qbs_compute_engine.sv', 'qbs_activation_context.sv']}
    own = {str(p.resolve()): digest(p) for p in [Path(__file__),
        Path(__file__).with_name('vrf_panel_attribution_README.md'), receipt_path, args.image_pins]}
    check_pins(evidence)
    check_pins(pins)
    check_pins(rtl)
    text = log_path.read_text()
    result = analyze(text, receipt)
    result['rejected_mutations'] = mutation_tests(text, receipt)
    for group in [evidence, pins, rtl, own]:
        check_pins(group)
    result.update(attribution_check='PASS', benchmark_pins_checked_pre_post=len(pins),
                  evidence_sha256=evidence, analyzer_inputs_sha256=own, reviewed_rtl_sha256=rtl,
                  image_pin_scope='Only the three attribution RTL files, not every historical build-helper pin.')
    args.output.mkdir(parents=True, exist_ok=False)
    target = args.output/'result.json'
    target.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n')
    (args.output/'receipt.json').write_text(json.dumps({'result_sha256': digest(target),
        'state': 'ATTRIBUTION_CHECK_PASS_PERFORMANCE_REGRESSION'}, indent=2)+'\n')
    print('VRF_PANEL_ATTRIBUTION_CHECK_PASS performance=REGRESSION output='+str(target))


if __name__ == '__main__':
    main()
