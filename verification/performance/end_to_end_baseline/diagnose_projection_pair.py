#!/usr/bin/env python3
"""Explain the measured pair without interpreting a cropped-N share as model time."""
import argparse
import json
from pathlib import Path

from audit import digest, require
from collect_projection_native import collect, paired
from check_projection_native import fields

WAIT = ('probe_weight_wait_no_outstanding_cycles', 'probe_weight_wait_response_idle_cycles',
        'probe_weight_wait_r_transfer_cycles', 'probe_weight_wait_r_blocked_cycles')


def explain(reports, raw_counters):
    require([r['wide'] for r in reports] == [0, 1], 'Wrong pair order')
    comparison = paired(*reports); totals = []
    same_work = ('ar', 'r_beats', 'payload_bytes', 'weight_bytes', 'activation_bytes',
                 'useful_pairs', 'fp_uop_issue', 'accumulator_updates')
    for report, raw in zip(reports, raw_counters):
        require(len(raw) == 24, 'Incomplete raw commands')
        summed = {k:sum(row[k] for row in raw) for k in (*same_work, 'weight_prefetch_wait_cycles', *WAIT)}
        require(sum(summed[k] for k in WAIT) == summed['weight_prefetch_wait_cycles'], 'Strict WAIT partition')
        totals.append(summed)
    require(all(totals[0][k] == totals[1][k] for k in same_work), 'Changed useful or physical command work')
    before, after = [r['measured'] for r in reports]
    dot_saved = before['dot_issue_count']-after['dot_issue_count']
    wait_added = totals[1]['weight_prefetch_wait_cycles']-totals[0]['weight_prefetch_wait_cycles']
    busy_saved = before['qbs_busy_cycles']-after['qbs_busy_cycles']
    require(dot_saved > 0 and wait_added >= 0 and busy_saved == dot_saved-wait_added,
            'Evidence does not fit dot-minus-exposed-wait explanation')
    require(before['region_cycles']-after['region_cycles'] ==
            before['execution_cycles']-after['execution_cycles'] == busy_saved and
            before['preparation_cycles'] == after['preparation_cycles'], 'CPU-stage explanation differs')
    return dict(comparison=comparison, unchanged_work={k:totals[0][k] for k in same_work},
        dot_issue_cycles_saved=dot_saved, extra_strict_weight_wait=wait_added,
        qbs_busy_cycles_saved=busy_saved, strict_wait=totals[1],
        preparation_fraction_of_this_candidate_region=after['preparation_cycles']/after['region_cycles'],
        ideal_ratio_if_only_new_weight_wait_were_removed=after['region_cycles']/(after['region_cycles']-wait_added),
        explanation='For this pair only: actual savings equal dot issue reduction minus additional strict weight wait',
        not_model_fraction='N=128 is a prefix; full operator N changes activation-preparation amortization',
        not_ddr_latency='R-transfer buckets observe shared-reader activity while compute waits, not weight-only DDR latency')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); receipt = args.pair.resolve(strict=True)
    prior = json.loads(receipt.read_text()); require(prior['state'] == 'REAL_QWEN3_SDK_RTL_PAIR_REAUDITED', 'Pair gate')
    reports = [collect(Path(r['run']), i) for i, r in enumerate(prior['reports'])]
    require(reports == prior['reports'], 'Pair replay drift')
    raw = [[fields(s, '[QBS_PERF]') for s in (Path(r['run'])/'work/run.vcs.log').read_text().splitlines()
            if s.startswith('[QBS_PERF] ')] for r in reports]
    result = dict(state='QWEN3_SDK_PAIR_CAUSAL_ACCOUNTING_PASS', pair=str(receipt),
                  pair_sha256=digest(receipt), diagnosis=explain(reports, raw),
                  source_pins={str(Path(__file__).resolve()):digest(__file__)},
                  model_performance_measured=False, area_measured=False)
    require(not args.output.exists(), 'Fresh diagnosis file required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__': main()
