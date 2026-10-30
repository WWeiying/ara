#!/usr/bin/env python3
"""Collect local retirement gates; this is not a SoC performance acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from run_tile_context_engine import check_geometry, check_log


def profile_gate(text, vectors):
    if re.search(r'Fatal:|Error:|UVM_ERROR|UVM_FATAL', text):
        raise ValueError('Profile simulation failed')
    expected = [tuple(map(int, r)) for r in re.findall(
        r'^CASE (\d+) (\d+) (\d+) (\d+) (\d+)$', vectors, re.M)]
    rows = [tuple(map(int, r)) for r in re.findall(
        r'^QBS RTL case (\d+) PASS profile=(\d+) M=(\d+) rows=(\d+) '
        r'pattern=(\d+) first_cycles=(\d+) repeat_cycles=(\d+)$', text, re.M)]
    if (len(expected) != 448 or [r[:5] for r in rows] != expected or
            any(min(r[5:]) <= 0 for r in rows) or
            text.splitlines().count('QBS profile engine PASS: 448 cases') != 1):
        raise ValueError('Incomplete profile arithmetic coverage')
    return dict(cases=len(rows), profiles=sorted({r[1] for r in rows}),
                m=sorted({r[2] for r in rows}), rows=sorted({r[3] for r in rows}))


def hold_gate(text, count=24):
    rows = re.findall(r'^QBS_REPLAY_HOLD_SUMMARY holds=(\d+) overlaps=(\d+) '
                      r'held_at_end=([01])$', text, re.M)
    if (rows != [(str(count), str(count), '0')] or
            len(re.findall(r'^QBS_REPLAY_HOLD cycle=', text, re.M)) != count):
        raise ValueError('Fault did not interrupt every deliberately held replay')
    return dict(holds=count, fault_overlaps=count, held_at_end=False)


def collect():
    out = ROOT / 'verification/out'
    base = out / 'qbs-tile-boundary-build-20261029-01'
    cand = out / 'qbs-retire-boundary-build-20261029-01'
    vectors = HERE.parent / 'qbs_command_vectors.txt'
    context_vectors = cand / 'context-vectors.txt'
    inputs = {}

    def read(path):
        inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text()

    runs = {}
    specs = (
        ('baseline', base/'baseline-full.log', 36, 1, 0, vectors),
        ('candidate', cand/'candidate.log', 36, 1, 0, vectors),
        ('candidate_gap3', cand/'candidate-gap3.log', 36, 1, 3, vectors),
        ('candidate_context', cand/'candidate-context.log', 12, 12, 0, context_vectors),
        ('baseline_context_held', out/'qbs-baseline-replay-build-20261029-01/baseline-context-gap3-held.log',
         12, 12, 3, context_vectors),
        ('candidate_context_held', out/'qbs-retire-replay-build-20261029-01/candidate-context-gap3-held.log',
         12, 12, 3, context_vectors),
    )
    for name, path, count, contexts, gap, vector in specs:
        text = read(path)
        result = check_log(text, count, contexts, gap)
        check_geometry(read(vector), result['direct'])
        if name.endswith('_held'):
            result['controlled_pressure'] = hold_gate(text)
        runs[name] = result
    old, new = runs['baseline']['direct'], runs['candidate']['direct']
    if [r[:-1] for r in old] != [r[:-1] for r in new]:
        raise ValueError('Mismatched numerical configurations')
    delta = [b[-1] - c[-1] for b, c in zip(old, new)]
    if min(delta) < 0:
        raise ValueError('Candidate local case regressed')
    arithmetic = profile_gate(read(out/'qbs-retire-profile-build-20261029-01/profile-stalls.log'),
                              read(HERE.parent/'qbs_rtl_vectors.txt'))
    for path in (HERE/'retire_candidate.sv', HERE/'replay_probe.sv',
                 HERE.parent/'qbs_engine_tb.sv', HERE.parent/'qbs_profile_engine_tb.sv',
                 Path(__file__), HERE.parent/'run_tile_context_engine.py'):
        read(path)
    return dict(state='LOCAL_GATES_PASS_NOT_SOC_ACCEPTED', runs=runs,
        arithmetic_with_result_pressure=arithmetic,
        diagnostic_cycle_sum=dict(baseline=sum(r[-1] for r in old),
            candidate=sum(r[-1] for r in new), faster=sum(d > 0 for d in delta),
            equal=delta.count(0), slower=sum(d < 0 for d in delta)),
        evidence_pins=inputs, full_compile_inventory_proven=False,
        unheld_gap3_capacity_suite='FAILED_OVERLAP_PRECONDITION_ON_BASELINE_AND_CANDIDATE',
        whole_model_speedup_measured=False, production_promoted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = collect()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['state'])
