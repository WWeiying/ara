#!/usr/bin/env python3
"""Fresh repair campaign, reusing only audited PASS results from stopped wave."""
from pathlib import Path
import sys

import run_timeout_repair as repair

batch, extension = repair.batch, repair.extension
SCRIPT = Path(__file__).resolve()
PRIOR = batch.ROOT / 'verification/out/vcs-dve-timeout-repair-20260927-01'
REUSE = ('extra-rvv-coverage_trap_state_quiet', 'extra-rvv-coverage_vlseg_quiet')


def validated_pass(plan, old, case, record):
    if plan['image'] != old['image']:
        raise ValueError('different simulation image')
    archived = next(c for c in old['cases'] if c['name'] == case['name'])
    for key in ('test', 'elf_sha256', 'oracle', 'coverage_test'):
        if archived[key] != case[key]:
            raise ValueError('different case contract: ' + key)
    if record['status'] != 'PASS' or not record['vdb_valid'] or not record['passed_only']:
        raise ValueError('reuse requires audited PASS and complete VDB')
    batch.check(archived['source_files'])
    batch.check(record['files'])
    if batch.base.inventory(Path(record['vdb'])) != record['vdb_files']:
        raise ValueError('changed VDB')
    return dict(record, reused=True, reused_from=str(PRIOR))


def prepare(output, previous, selection):
    repair.prepare(output, previous, selection)
    plan = batch.read(output / 'plan.json')
    old = batch.frozen(PRIOR, all_cases=True)
    for case in plan['cases']:
        if case.get('test') == 'rvv:coverage_vl1r_quiet':
            case['timeout_s'] = 900
            case['timeout_rationale'] = (
                'Quiet ELF reaches CASE1/2/3/4 at cycles388/13967/38121/82240; '
                'at cycle124862 it advances in bounded CASE4 memset. '
                'Work scales with register group1/2/4/8; extrapolated full '
                'work about180-210k cycles (~450-510s at measured throughput). '
                '900s accommodates contention; preserve all five cases in order.')
        if case['name'] not in REUSE:
            continue
        path = PRIOR / 'outcomes' / (case['name'] + '.json')
        record = validated_pass(plan, old, case, batch.read(path))
        batch.save(output / 'outcomes' / path.name, record)
        plan['reused'].append(case['name'])
        plan['files'].update(batch.pins([path]))
        batch.publish(output, record)
    plan['files'].update(batch.pins([SCRIPT, Path(repair.__file__), PRIOR / 'plan.json',
                                     PRIOR / 'plan.sha256.json']))
    batch.save(output / 'plan.json', plan)
    batch.save(output / 'plan.sha256.json', batch.pins([output / 'plan.json']))
    batch.frozen(output, all_cases=True)
    print('REUSED two audited PASS results; 38 executions pending', flush=True)


def main():
    extension.SCRIPT = repair.gap.SCRIPT = batch.SCRIPT = SCRIPT
    extension.prepare = prepare
    result = extension.main()
    if result and '--execute' in sys.argv:
        output = Path(sys.argv[sys.argv.index('--output') + 1])
        stops = sorted(output.glob('repair_stop_*.json'))
        if stops:
            state = batch.read(output / 'checkpoint.json')
            state['reason'] = 'Repair non-PASS: ' + ', '.join(
                batch.read(p)['case'] for p in stops)
            batch.save(output / 'checkpoint.json', state)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
