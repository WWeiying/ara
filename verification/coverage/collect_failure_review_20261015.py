#!/usr/bin/env python3
"""Successor ledger and PASS-only current-image coverage; never edit old results."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import time

import replay_historical_extensions_20261015 as base
from run_vcs_dve_batch import valid_vdb
from control_scope_audit_20261015 import PROFILES

ROOT = base.ROOT
RUN = ROOT / 'verification/out/full-regression-20261015-01'
CORE = RUN / 'full-regression-core-20261015-01'
REVIEW = ROOT / 'verification/out/full-regression-failure-review-20261015-01'
REPLAYS = ROOT / 'verification/out/full-regression-repair-replays-20261015-01'


def probe_accepted(detail):
    claimed = detail.get('functional_status') == 'PASS' or detail['status'] == 'SEMANTIC_PASS_NOT_ADMITTED'
    if not claimed:
        return False
    needed = {'execution', 'native', 'dispatch'}
    if detail['index'] in (761, 771, 786, 788, 791, 792, 794):
        needed |= {'scalar', 'vector'}
    if detail['index'] in (761, 789, 790):
        needed |= {'conversion', 'wave'}
    if detail['index'] in (789, 790):
        needed |= {'source_context', 'perf'}
    if detail['index'] == 771:
        needed |= {'stdout'}
    base.require(all(detail['components'].get(k, {}).get('status') == 'PASS' for k in needed),
                 'architectural PASS claim lacks mandatory independent components')
    return True


def ledger(probe_audit):
    plan = base.read(CORE / 'plan.json')
    rows = {}
    for case in plan['cases']:
        index = int(case['name'][1:5])
        path = CORE / 'outcomes' / (case['name'] + '.json')
        old = base.read(path)
        rows[index] = dict(index=index, status=old['status'], original_status=old['status'],
                           vdb=old.get('vdb'), coverage_test=old.get('coverage_test'),
                           evidence=[str(path)])
    extensions = base.read(RUN / 'extensions/complete.json')
    for index, old in extensions['cases'].items():
        index = int(index)
        rows[index] = dict(index=index, status=old['status'], original_status=old['status'],
                           vdb=old.get('vdb'), coverage_test=base.option(old['command'], '-cm_name'),
                           evidence=[str(RUN / f'extensions/e{index:04d}/result.json')])
    base.require(set(rows) == set(range(798)), 'exact798 selection required')
    controls = base.read(REVIEW / 'control-scope-final/summary.json')
    base.require(len(controls['cases']) == len(PROFILES) and
                 {p['index'] for p in controls['cases']} == set(PROFILES),
                 'exact17 reviewed control scopes required')
    fence = base.read(REVIEW / 'fence/summary.json')
    fence_ok = {r['index'] for r in fence['fences']
                if r['status'] == 'FOCUSED_ARCHITECTURAL_PASS_NOT_FULL_ORIGINAL_ADMISSION'}
    for proof in controls['cases']:
        index = proof['index']
        base.require(proof['status'] == 'PASS', 'control scope audit did not pass')
        if index in (638, 727):
            base.require(index in fence_ok, 'missing FENCE supplemental architecture proof')
        base.verify(proof['pins'])
        rows[index].update(status='PASS', scope=proof['scope'],
                           evidence=rows[index]['evidence'] + [str(REVIEW / 'control-scope-final' / f'e{index:04d}.json'),
                                                             str(REVIEW / 'fence/summary.json')])
    probes = base.read(probe_audit)
    expected_probes = {761, 771, 782, 785, 786, 788, 789, 790, 791, 792, 794}
    base.require(len(probes['cases']) == 11 and {p['index'] for p in probes['cases']} == expected_probes,
                 'exact11 probe audits required')
    for proof in probes['cases']:
        index = proof['index']
        detail = base.read(Path(proof['report']))
        base.require(detail['index'] == index, 'probe report identity mismatch')
        # Only the auditor's explicit architectural verdict can admit a test.
        # Clearing Tcl echo diagnostics is not a functional oracle.
        if probe_accepted(detail):
            base.verify(detail['input_pins'])
            rows[index].update(status='PASS', scope='independently audited current-image architectural results',
                               micro_witness=detail.get('micro_witness', {'status': 'CHECKER_REQUIRED'}))
        else:
            rows[index].update(status='CHECKER_REQUIRED', reason=detail.get('missing_components'))
        rows[index]['evidence'].append(proof['report'])
    for name, index in (('c0375', 375), ('e0784', 784)):
        path = REPLAYS / name / 'result.json'
        result = base.read(path)
        rows[index].update(status=result['status'], evidence=rows[index]['evidence'] + [str(path)])
        if result['status'] == 'PASS':
            receipt = base.read(REPLAYS / name / 'simulation-exit.json')
            base.require(type(receipt['returncode']) is int and receipt['returncode'] == 0 and
                         receipt['executed'] is True and not receipt['timed_out'] and not receipt['cancelled'],
                         'typed normal successor terminal required')
            rows[index].update(vdb=result['vdb'])
            if index == 784:
                full = base.read(REPLAYS / name / 'full-architecture/qualification.json')
                base.require(full['status'] == 'PASS', 'full VALU architecture oracle required')
            else:
                base.require(result['audit']['benchmark']['mismatches'] == '0', 'QBS mismatches')
    return plan, [rows[i] for i in range(798)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wait-for-replays', action='store_true')
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    base.require(not output.exists(), 'fresh successor output required')
    output.mkdir(parents=True)
    state = dict(status='WAITING_FOR_REPLAYS')
    base.save(output / 'status.json', state)
    deadline = time.monotonic() + 3600
    try:
        while True:
            p = REPLAYS / 'progress.json'
            replay_state = base.read(p) if p.exists() else {}
            if replay_state.get('status') in ('PASS', 'COMPLETE_WITH_NONPASS'):
                break
            base.require(args.wait_for_replays and time.monotonic() < deadline,
                         'bounded replay successor still incomplete; no partial admission')
            time.sleep(30)
        plan, rows = ledger(args.probe_audit)
        counts = dict(Counter(r['status'] for r in rows))
        base.save(output / 'case-ledger.json', dict(total=798, counts=counts, cases=rows,
                   old_evidence_modified=False, no_old_microcoverage_gain_claim=True))
        base.verify(plan['image'])
        accepted = [r for r in rows if r['status'] == 'PASS']
        databases = [plan['design_vdb']]
        for row in accepted:
            vdb = Path(row['vdb'])
            valid_vdb(vdb, row['coverage_test'], plan['simv'])
            databases.append(str(vdb))
        base.require(len(set(databases)) == len(databases), 'duplicate current-image VDB')
        inputs = output / 'pass-vdbs.txt'
        inputs.write_text('\n'.join(databases) + '\n')
        state.update(status='FUNCTIONALLY_AUDITED', total=798, counts=counts,
                     passed=len(accepted), partial_or_unreviewed_excluded=798 - len(accepted))
        base.save(output / 'status.json', state)
        if args.collect:
            state['status'] = 'DVE_RUNNING'
            base.save(output / 'status.json', state)
            command = ['bash', str(ROOT / 'verification/coverage/dve_hierarchy/run_dve_coverage.sh'),
                       str(output / 'dve'), '--inputs-file', str(inputs)]
            base.save(output / 'dve.command.json', dict(command=command))
            with (output / 'dve.log').open('x') as stream:
                result = subprocess.run(command, cwd=ROOT, env=dict(os.environ,
                    DVE_COVERAGE_TIMEOUT='1800', DVE_WAIVERS='auto'), stdout=stream,
                    stderr=subprocess.STDOUT, timeout=1920, check=False)
            base.require(result.returncode == 0 and (output / 'dve/summary.csv').is_file(),
                         'DVE export failed; do not publish partial percentages')
            state['status'] = 'COMPLETE' if len(accepted) == 798 else 'COMPLETE_WITH_NONPASS'
        base.verify(plan['image'])
        base.save(output / 'status.json', state)
        print(json.dumps(state))
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        base.save(output / 'status.json', state)
        raise


if __name__ == '__main__':
    main()
