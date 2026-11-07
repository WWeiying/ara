#!/usr/bin/env python3
"""Replay actual Prefill service; distinguish issue-port bounds from utilization."""
import argparse
from collections import Counter
import json
from pathlib import Path

from audit import digest, require, verify_pins
import continue_supply_sdk as campaign
from check_projection_native import fields

ROOT = campaign.RUNS / 'e2e_physical_supply_sdk_pair_20261106_01'
PARENT_SHA = '4e2b1fcd231cb3534d2224a60f70ec018fcf906e51b36a00dabd2070d98a1ae0'
FP = campaign.RUNS / 'e2e_physical_wide_soc_inputs_20261106_01/source/hardware/src/vlsu/qbs/qbs_fp_accumulator.sv'
FP_SHA = '13a400d7daa62779e6f829237365c4df7b31fbd4f2f6024491c1fb59468f4d60'


def command_budget(command, profile):
    require(profile in (1, 2) and command['m'] == 4 and command['n'] == 32 and
            command['activation_access'] == 0 and command['success'] == 1 and command['fault'] == 0,
            'Budget only covers native M4 Q4_K/Q6_K with Q8_K activation and no context')
    updates = command['accumulator_updates']
    require(updates == 1024 and command['useful_pairs'] == 262144 and
            command['dot_active_cycles'] == 4096, 'Unexpected command geometry/work')
    # Reviewed state sequence: affine has two I2F, two MUL and two FMADD;
    # symmetric has one I2F, one MUL and one FMADD. Q8_K has FP32 scale,
    # so the independent FP16-by-FP16 half-scale port is ineligible here.
    casts, multiplies, fmas = (2, 2, 2) if profile == 1 else (1, 1, 1)
    casts *= updates; multiplies *= updates; fmas *= updates
    require(command['fp_uop_issue'] == casts + multiplies + fmas,
            'Actual FP uops do not match the reviewed per-update sequence')
    arithmetic = multiplies + fmas
    current_dot = command['dot_active_cycles']
    hypothetical_dot = (command['useful_pairs'] + 127) // 128
    return dict(profile=profile, updates=updates, casts=casts, multiplies=multiplies, fmas=fmas,
        arithmetic_port_issue_floor=arithmetic, cast_port_issue_floor=casts,
        current_dot_issue_cycles=current_dot, hypothetical_128_product_dot_issue_floor=hypothetical_dot,
        actual_r_beat_service_floor=command['r_beats'],
        hypothetical_fixed_ports_command_service_floor=max(hypothetical_dot, arithmetic, casts, command['r_beats']),
        arithmetic_floor_exceeds_hypothetical_dot=arithmetic > hypothetical_dot)


def explain(reports, rows):
    require(set(reports) == set(rows) == {128, 256}, 'Both actual physical widths required')
    require(all(len(rows[w]) == 128 for w in rows), 'All actual commands required')
    sums, budgets = {}, {}
    for width in (128, 256):
        total = Counter()
        for row in rows[width]:
            total.update({k:v for k,v in row.items() if k.startswith(('phase_', 'probe_')) or
                k in ('busy_cycles', 'dot_active_cycles', 'fp_uop_issue', 'accumulator_updates',
                      'weight_prefetch_wait_cycles')})
        require(sum(v for k,v in total.items() if k.startswith('phase_')) == total['busy_cycles'],
                'Phase counters are not a complete partition')
        require(total['busy_cycles'] == reports[width]['measured']['qbs_busy_cycles'], 'Raw busy differs')
        sums[width] = dict(total)
        budgets[width] = [command_budget(row, 1 if i < 96 else 2) for i,row in enumerate(rows[width])]
    a,b = sums[128], sums[256]
    require(a.keys() == b.keys(), 'Probe inventories differ')
    invariant = ('dot_active_cycles', 'fp_uop_issue', 'accumulator_updates',
                 'probe_compute_without_dot_issue_cycles', 'probe_fp_busy_cycles',
                 'probe_profile_correction_pending_cycles', 'probe_profile_result_pending_cycles')
    require(all(a[k] == b[k] for k in invariant), 'Arithmetic or diagnostic activity changed')
    saved = a['busy_cycles'] - b['busy_cycles']
    require(saved == a['phase_weight_cycles']-b['phase_weight_cycles'] and
            a['phase_compute_cycles']+a['phase_overlap_cycles'] ==
            b['phase_compute_cycles']+b['phase_overlap_cycles'], 'Weight-only phase explanation contradicted')
    for w in sums:
        require(sums[w]['probe_fp_input_blocked_cycles'] ==
                sums[w]['probe_profile_result_blocked_cycles'] == 0, 'Actual FP backpressure is not zero')
    return dict(counters=sums, busy_cycles_saved=saved,
        weight_phase_cycles_saved=saved,
        compute_plus_overlap_cycles_unchanged=a['phase_compute_cycles']+a['phase_overlap_cycles'],
        unchanged_arithmetic_activity={k:a[k] for k in invariant},
        per_profile_port_budgets256=[dict(profile=p,
            commands=sum(v['profile']==p for v in budgets[256]),
            one_representative=next(v for v in budgets[256] if v['profile']==p),
            summed_fixed_ports_service_floor=sum(v['hypothetical_fixed_ports_command_service_floor']
                                                for v in budgets[256] if v['profile']==p)) for p in (1,2)],
        actual_product_rate=64, hypothetical_product_rate=128,
        hypothetical_hardware_implemented=False, hypothetical_performance_measured=False,
        architectural_conclusion='Do not double integer products alone: affine Q4_K would retain '
            '4096 arithmetic issues per command on the single FP arithmetic port, versus 2048 dot issues',
        counter_semantics=['fp_uop_issue sums separate arithmetic, I2F and half-scale handshakes',
            'probe_fp_busy includes live entry state; it is not FP arithmetic functional utilization',
            'compute-only and overlap phases may reclassify when memory finishes earlier',
            'Port-service floors may overlap; they are not additive stalls or predicted execution time'])


def main(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(campaign.RUNS), 'Fresh sole-verification output required')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}; result = dict(state='FAIL', whole_model=False, synthesis_run=False, new_simulations=0)
    try:
        bind = campaign.runner.bind
        bind(pins, ROOT/'result.json', PARENT_SHA); bind(pins, FP, FP_SHA)
        source = FP.read_text()
        for anchor in ('Width:          32,', "EnableVectors: 1'b0,", "parameter bit SplitIssue = 1'b1,",
                       'assign fp_fire = fp_in_valid && fp_in_ready;',
                       "fp_uop_issue_o <= fp_uop_issue_o + 32'(fp_fire) + 32'(cast_fire) + 32'(half_fire);",
                       "qbs_activation_scale_format(request_activation_profile_i) == QBS_SCALE_FP16"):
            require(anchor in source, 'Reviewed FP issue contract changed')
        parent = json.loads((ROOT/'result.json').read_text())
        require(parent['state'] == 'PHYSICAL_SUPPLY_SDK_PAIR_PASS' and parent['post_pins_match'], 'Parent not passed')
        bind(pins, ROOT/'source-pins.json', parent['source_pins_sha256'])
        verify_pins(json.loads((ROOT/'source-pins.json').read_text()))
        reports = {w:campaign.collect(ROOT/('prefill'+str(w)), 'prefill', w) for w in (128,256)}
        rows = {}
        for w in (128,256):
            root = ROOT/('prefill'+str(w)); bind(pins, root/'result.json'); bind(pins, root/'source-pins.json')
            log = root/'work/run.vcs.log'; bind(pins, log)
            rows[w] = [fields(s, '[QBS_PERF]') for s in log.read_text().splitlines() if s.startswith('[QBS_PERF] ')]
        for path in (Path(__file__), Path(__file__).with_name('test_diagnose_supply_prefill.py')): bind(pins, path)
        result.update(state='PHYSICAL_PREFILL_RESOURCE_DIAGNOSIS_PASS', diagnosis=explain(reports,rows),
                      parent_result_sha256=PARENT_SHA, fp_source_sha256=FP_SHA,
                      independently_replayed=True, current_pair_performance_measured=True,
                      future_architecture_performance_measured=False)
        verify_pins(pins)
        result['source_pins'] = pins
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
