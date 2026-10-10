#!/usr/bin/env python3
"""Resume eight unfinished AKV tests without rebuilding RTL or changing ELFs."""
from pathlib import Path
import sys

import run_timeout_repair as repair
from resume_timeout_repair import validated_pass

batch, extension = repair.batch, repair.extension
SCRIPT = Path(__file__).resolve()
PRIOR = batch.ROOT / 'verification/out/vcs-dve-timeout-repair-20260927-04'


def matching_case(case, archived):
    for key in ('test', 'elf_sha256', 'oracle', 'coverage_test'):
        if case[key] != archived[key]:
            raise ValueError('archived AKV contract changed: ' + key)
    batch.check(archived['source_files'])


def prepare(output, previous, selection):
    repair.prepare(output, previous, selection)
    plan = batch.read(output / 'plan.json')
    old = batch.frozen(PRIOR, all_cases=True)
    if plan['image'] != old['image']:
        raise ValueError('different simulation image')
    archived = {c['name']: c for c in old['cases']}
    resumed, reused = [], []
    for case in plan['cases']:
        if case['name'] in plan['reused']:
            continue
        matching_case(case, archived[case['name']])
        path = PRIOR / 'outcomes' / (case['name'] + '.json')
        record = batch.read(path) if path.exists() else None
        if record and record['status'] == 'PASS':
            record = validated_pass(plan, old, case, record)
            record['reused_from'] = str(PRIOR)
            batch.save(output / 'outcomes' / path.name, record)
            plan['reused'].append(case['name'])
            plan['files'].update(batch.pins([path]))
            batch.publish(output, record)
            reused.append(case['test'])
            continue
        if record:
            if record['status'] != 'TIMEOUT':
                raise ValueError('unexpected unanalysed failure')
            batch.check(record['files'])
            plan['files'].update(batch.pins([path]))
            plan['files'].update(record['files'])
            case['previous_outcome'] = str(path)
        if case['test'] == 'app:coverage_akv_portability_mixed':
            case['timeout_s'] = 1800
            case['timeout_rationale'] = (
                'Same ELF. Reference entered at cycle67351; all65 max-score '
                'tokens and4160 dimensions complete at238117. At243428, '
                'second-pass token1 dimension46 advances, native entry unreached. '
                'Two score sweeps plus55 unmasked PV reductions and native '
                'execution estimate550-650k cycles (~23-27min at measured '
                '406cycles/s). Bound1800s retains full oracle and65-token tail.')
        resumed.append(case['test'])
    if len(reused) != 14 or len(resumed) != 8:
        raise ValueError('unexpected repair scope')
    plan['files'].update(batch.pins([SCRIPT, Path(repair.__file__),
        Path(sys.modules[validated_pass.__module__].__file__),
        PRIOR / 'plan.json', PRIOR / 'plan.sha256.json']))
    plan['repair_resume'] = dict(previous=str(PRIOR), reused=reused, pending=resumed)
    batch.save(output / 'plan.json', plan)
    batch.save(output / 'plan.sha256.json', batch.pins([output / 'plan.json']))
    batch.frozen(output, all_cases=True)
    print('REUSED14 audited AKV PASS results;8 exact-ELF executions pending', flush=True)


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
