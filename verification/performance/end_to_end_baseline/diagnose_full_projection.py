#!/usr/bin/env python3
"""Causal accounting of the actual full-N QKV pair, without model extrapolation."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins
from collect_full_projection import collect, compare
from check_projection_native import fields
from diagnose_projection_pair import WAIT


def explain(reports, raw):
    comparison = compare(*reports)
    same = ('ar','r_beats','payload_bytes','weight_bytes','activation_bytes','useful_pairs',
            'fp_uop_issue','accumulator_updates')
    totals = []
    for rows in raw:
        require(len(rows) == 128,'Incomplete full-output commands')
        total = {key:sum(row[key] for row in rows) for key in (*same,'weight_prefetch_wait_cycles',*WAIT)}
        require(sum(total[key] for key in WAIT) == total['weight_prefetch_wait_cycles'],'WAIT partition')
        totals.append(total)
    require(len(totals) == 2 and all(totals[0][key] == totals[1][key] for key in same),'Changed command work')
    a,b = [r['measured'] for r in reports]
    dot = a['dot_issue_count']-b['dot_issue_count']
    wait = totals[1]['weight_prefetch_wait_cycles']-totals[0]['weight_prefetch_wait_cycles']
    busy = a['qbs_busy_cycles']-b['qbs_busy_cycles']
    require(dot > 0 and wait >= 0 and busy == dot-wait and
            a['execution_cycles']-b['execution_cycles'] == a['region_cycles']-b['region_cycles'] == busy and
            a['preparation_cycles'] == b['preparation_cycles'],'Observed phases do not fit this causal explanation')
    return dict(comparison=comparison,unchanged_work={key:totals[0][key] for key in same},
                dot_issue_cycles_saved=dot,additional_strict_weight_wait=wait,qbs_busy_cycles_saved=busy,
                baseline_strict_wait=totals[0],candidate_strict_wait=totals[1],
                ideal_ratio_if_only_additional_wait_removed=b['region_cycles']/(b['region_cycles']-wait),
                limitations=['Identity is specific to this pair, not a general additive stall model',
                             'Full N but only four prompt rows; no complete GGML/model timing',
                             'Strict WAIT buckets observe shared-reader traffic, not weight-only DDR latency'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); pair = args.pair.resolve(strict=True); out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False); result = dict(state='CHECKING',whole_model=False,area_measured=False)
    try:
        pins = {str(path):digest(path) for path in (Path(__file__),Path(__file__).with_name('audit.py'),
                Path(__file__).with_name('collect_full_projection.py'),Path(__file__).with_name('diagnose_projection_pair.py'),pair)}
        accepted = json.loads(pair.read_text()); require(accepted['state'] == 'FULL_QWEN3_QKV_SDK_PAIR_REAUDITED','Pair gate')
        reports = [collect(Path(row['run']),i) for i,row in enumerate(accepted['reports'])]
        require(reports == accepted['reports'],'Full pair replay drift')
        raw = [[fields(s,'[QBS_PERF]') for s in (Path(row['run'])/'work/run.vcs.log').read_text().splitlines()
                if s.startswith('[QBS_PERF] ')] for row in reports]
        diagnosis = explain(reports,raw); verify_pins(pins)
        result.update(state='FULL_QWEN3_QKV_CAUSAL_ACCOUNTING_PASS',diagnosis=diagnosis,pair=str(pair),
                      pair_sha256=digest(pair),source_pins=pins)
    except BaseException as exc: result.update(state='FAIL',error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':main()
