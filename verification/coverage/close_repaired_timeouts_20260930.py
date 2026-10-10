#!/usr/bin/env python3
"""One independent attempt for the repaired collection's 14 wall timeouts."""
import argparse
from collections import Counter
import copy
import csv
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import sys

import run_full_recollection_20260928 as full

SCRIPT = Path(__file__).resolve()
SOURCE = full.ROOT / 'verification/out/repaired-aligned-600-20260930-01'
SERVICE = 'ara-repaired-timeout-closure-20260930-01.service'
original_frozen = full.frozen


def budget(case):
    return {'app:akv_portability_smoke': 2400,
            'app:akv_d256_reuse_smoke': 7200}.get(case['source_name'], 1200)


def selected(source):
    plan = original_frozen(source, all_cases=True)
    state = full.read(source / 'checkpoint.json')
    full.require(state['status'] == 'COMPLETE_WITH_FAILURES' and
                 state['total'] == state['completed'] == 600 and
                 state['counts'] == {'PASS': 586, 'TIMEOUT': 14}, 'expected frozen 586/600 collection')
    rows = [c for c in plan['cases'] if state['cases'][c['name']]['status'] == 'TIMEOUT']
    full.require(len(rows) == 14 and all(c['kind'] == 'directed' and c['timeout_s'] == 300 for c in rows),
                 'unexpected timeout selection')
    full.require(Counter(budget(c) for c in rows) == {1200: 12, 2400: 1, 7200: 1}, 'budget membership drift')
    for c in rows:
        old = full.read(source / 'outcomes' / (c['name'] + '.json'))
        summary = full.read(source / 'results' / c['name'] / 'summary.json')
        full.require(old['status'] == summary[0]['status'] == 'TIMEOUT' and
                     old['elf_sha256'] == c['elf_sha256'] and
                     summary[0]['reason'] == 'timeout after 300s', 'original timeout evidence drift')
        full.check(old['files'])
    return plan, rows


def prepare(output):
    full.require(not output.exists(), 'new independent attempt directory required')
    original, rows = selected(SOURCE)
    output.mkdir(parents=True)
    for directory in ('inputs', 'logs', 'outcomes'):
        (output / directory).mkdir()
    plan = copy.deepcopy(original)
    plan['cases'] = copy.deepcopy(rows)
    plan['service'] = SERVICE
    for c in plan['cases']:
        c['timeout_s'] = budget(c)
        c['directed_test']['timeout_s'] = c['timeout_s']
    config = output / 'inputs/coverage-wrapper.json'
    wrapper = output / 'inputs/coverage_simv'
    full.save(config, {'simv': plan['simv'], 'image': plan['image'], 'results': str(output / 'results')})
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(full.SCRIPT),
                       '--coverage-exec', str(config)]) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + '.daidir').symlink_to(Path(plan['simv'] + '.daidir'), target_is_directory=True)
    shutil.copyfile(SOURCE / 'inputs/simulator.conf', output / 'inputs/simulator.conf')
    plan.update(wrapper=str(wrapper), wrapper_image=full.batch.simulation_image(wrapper))
    policy = output / 'closure-policy.json'
    full.save(policy, {'source': str(SOURCE), 'service': SERVICE, 'workers': 8,
        'attempts_per_case': 1, 'budgets': {c['name']: c['timeout_s'] for c in plan['cases']},
        'basis': 'User-approved plan: 12 cases 1200s, AKV portability 2400s, D256 reuse 7200s; host wall budget only. Historical results support diagnosis/budget, never new-image coverage.',
        'prefix_policy': 'exact complete CSV rows including cycles; ignore an incomplete final old row',
        'source_metadata': full.pins([SOURCE / n for n in ('plan.json', 'plan.sha256.json', 'checkpoint.json', 'collection.json', 'dve-inputs.before.json', 'dve-inputs.after.json', 'dve-inputs.txt')]),
        'source_outcomes': full.pins((SOURCE / 'outcomes').glob('*.json'))})
    plan['files'].update(full.pins([SCRIPT, policy, config, wrapper, output / 'inputs/simulator.conf']))
    full.save(output / 'plan.json', plan)
    full.save(output / 'plan.sha256.json', full.pins([output / 'plan.json']))
    full.save(output / 'checkpoint.json', {'status': 'PREPARED', 'total': 14, 'completed': 0,
        'cases': {}, 'workers': 8, 'simulations_started': False, 'coverage_status': 'PENDING'})
    frozen(output, all_cases=True)
    print('READY: 14 attempts, 8 workers; original 586 PASS and reports preserved')


def frozen(output, case=None, all_cases=False):
    policy = full.read(output / 'closure-policy.json')
    full.check(policy['source_metadata'])
    full.check(policy['source_outcomes'])
    original_frozen(Path(policy['source']), all_cases=all_cases)
    return original_frozen(output, case, all_cases)


def prefix(old, new):
    with old.open() as left, new.open() as right:
        a, b = csv.reader(left), csv.reader(right)
        header = next(a)
        if next(b, None) != header:
            return {'status': 'FAIL', 'row': 0, 'reason': 'trace header differs'}
        count = 0
        for row in a:
            if len(row) != len(header):
                return {'status': 'PASS', 'rows': count, 'incomplete_old_tail': True}
            actual = next(b, None)
            if actual != row:
                return {'status': 'FAIL', 'row': count + 1, 'expected': row, 'actual': actual}
            count += 1
        return {'status': 'PASS', 'rows': count}


def worker(output, name):
    plan = frozen(output)
    full.require(name in {c['name'] for c in plan['cases']}, 'cannot rerun a passed case')
    rc = full.worker(output, name)
    path = output / 'outcomes' / (name + '.json')
    item = full.read(path)
    if rc:
        return rc
    old = list((SOURCE / 'results' / name).rglob('commit_trace.csv'))
    new = list((output / 'results' / name).rglob('commit_trace.csv'))
    full.require(len(old) == len(new) == 1, 'missing/ambiguous prefix trace')
    report = prefix(old[0], new[0])
    audit = output / 'results' / name / 'execution-prefix-audit.json'
    full.save(audit, report)
    item['files'].update(full.pins([audit]))
    if report['status'] != 'PASS':
        item.update(status='FAIL', passed_only=False, reason='execution prefix differs; root cause analysis required')
    if item['status'] == 'FAIL':
        item['root_cause_required'] = True
    full.save(path, item)
    full.batch.publish(output, item)
    # Stop new dispatch on a result mismatch; retain every completed first attempt.
    return 1 if item['status'] == 'FAIL' else 0


def summarize(output, plan):
    original = original_frozen(SOURCE, all_cases=True)
    retry_names = {c['name'] for c in plan['cases']}
    outcomes, passed = [], []
    for c in original['cases']:
        owner = output if c['name'] in retry_names else SOURCE
        item = full.read(owner / 'outcomes' / (c['name'] + '.json'))
        full.require(item['name'] == c['name'] and item['elf_sha256'] == c['elf_sha256'] and
                     item['contract'] == c['contract'], 'outcome contract drift')
        full.check(item['files'])
        vdb = Path(item['vdb']).resolve()
        full.require(vdb.is_relative_to(owner / 'results' / c['name']), 'foreign VDB')
        if item['status'] == 'PASS':
            full.require(item['passed_only'] and item['vdb_valid'] and not item['reused'], 'unadmitted PASS')
            full.require(full.batch.valid_vdb(vdb, c['coverage_test'], plan['simv']) == item['vdb_files'], 'VDB drift')
            passed.append(item)
        else:
            full.require(not item['passed_only'], 'failed case admitted')
        outcomes.append(item)
    full.save(output / 'all-outcomes.json', outcomes)
    databases = {plan['design_vdb']: plan['design_files'], **{i['vdb']: i['vdb_files'] for i in passed}}
    full.require(len(databases) == len(passed) + 1, 'duplicate VDB')
    full.base.pure_design(Path(plan['design_vdb']))
    full.require(all(full.base.inventory(Path(p)) == h for p, h in databases.items()), 'VDB drift before DVE')
    full.save(output / 'dve-inputs.before.json', databases)
    inputs = output / 'dve-inputs.txt'
    inputs.write_text('\n'.join(databases) + '\n')
    target = output / 'dve'
    full.require(full.batch.invoke(['bash', str(full.DVE / 'run_dve_coverage.sh'), str(target),
        '--inputs-file', str(inputs)], output / 'logs/dve.log', plan['dve_outer_timeout_s'],
        {'DVE_COVERAGE_TIMEOUT': str(plan['dve_timeout_s']), 'DVE_WAIVERS': 'auto'}) == 0, 'DVE export failed')
    expected = [str(Path(i['vdb']).with_suffix('') / i['coverage_test']) for i in passed]
    full.require((target / 'selected_tests.txt').read_text().splitlines() == expected and
                 (target / 'inputs.txt').read_text().splitlines() == list(databases), 'DVE selection drift')
    after = {p: full.base.inventory(Path(p)) for p in databases}
    full.save(output / 'dve-inputs.after.json', after)
    full.require(after == databases, 'DVE modified inputs')
    waiver = full.read(target / 'waiver_status.json')
    full.require(waiver['status'] in ('APPLIED', 'NOT_APPLICABLE_UNREVIEWED_DESIGN'), 'unexpected waiver state')
    reports = [target / n for n in ('summary.csv', 'waiver_status.json', 'selected_tests.txt', 'inputs.txt')]
    if waiver['status'] == 'APPLIED':
        reports += [target / 'summary_waived.csv', target / 'exclusions.el']
    full.save(output / 'collection.json', {'status': 'PASS' if len(passed) == 600 else 'COMPLETE_WITH_FAILURES',
        'total': 600, 'passed': len(passed), 'counts': dict(Counter(i['status'] for i in outcomes)),
        'retained_current_image_passes': 586, 'historical_vdb_reuse': False, 'image': plan['image'],
        'source': str(SOURCE), 'waiver': waiver, 'reports': full.pins(reports),
        'failed_cases_excluded': [i['name'] for i in outcomes if i['status'] != 'PASS']})


def execute(output):
    full.base.check_service()
    with (full.ROOT / 'verification/out/.batch-vcs.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = frozen(output, all_cases=True)
        state = full.read(output / 'checkpoint.json')
        full.require(state['status'] == 'PREPARED', 'single attempt only')
        state.update(status='RUNNING', phase='14 bounded attempts', simulations_started=True)
        full.save(output / 'checkpoint.json', state)
        try:
            full.original_schedule(output, [c['name'] for c in plan['cases']], 8)
            state = full.read(output / 'checkpoint.json')
            full.require(state['completed'] == 14, 'incomplete attempts')
            state.update(phase='DVE merge', coverage_status='RUNNING')
            full.save(output / 'checkpoint.json', state)
            summarize(output, plan)
            frozen(output, all_cases=True)
            state.update(status=full.read(output / 'collection.json')['status'], phase='complete', coverage_status='COMPLETE')
            full.save(output / 'checkpoint.json', state)
            return 0 if state['status'] == 'PASS' else 1
        except Exception as error:
            state = full.read(output / 'checkpoint.json')
            state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
            full.save(output / 'checkpoint.json', state)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--worker')
    mode.add_argument('--directed')
    args = parser.parse_args()
    output = full.base.checked_output(args.output)
    os.environ['PYTHONPATH'] = str(full.ROOT / 'verification')
    for key in list(os.environ):
        if key.startswith(('ARA_UVM_', 'ARA_CONTRACT_', 'ARA_VCS_')):
            del os.environ[key]
    if args.prepare:
        prepare(output)
        return 0
    full.require(os.environ.get('ARA_CHECKPOINT_UNIT') == SERVICE and os.environ.get('INVOCATION_ID'),
                 'registered closure service required')
    full.batch.SCRIPT = SCRIPT
    full.frozen = full.batch.frozen = frozen
    full.batch.commands = full.commands
    if args.worker:
        return worker(output, args.worker)
    if args.directed:
        plan = frozen(output)
        full.require(args.directed in {c['name'] for c in plan['cases']}, 'case outside retry selection')
        return full.batch.directed(output, args.directed)
    return execute(output)


if __name__ == '__main__':
    raise SystemExit(main())
