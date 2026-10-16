"""Count explicit release/report evidence by ELF identity, never by snapshots.

Callers select the campaign's board reports. References, negative controls and
unrelated-image reports must not be passed as board evidence.
"""
from collections import Counter
import re


def inventory(manifests, reports):
    catalog = {}
    evidence = {}
    numerical_results = set()
    for source, manifest in manifests:
        seen = set()
        for case in manifest['cases']:
            key = (case['name'], case['sha256'])
            if key in seen:
                raise ValueError('Duplicate release ELF identity')
            seen.add(key)
            if key in catalog and catalog[key]['case']['pass_marker'] != case['pass_marker']:
                raise ValueError('Same ELF has conflicting numerical markers')
            catalog.setdefault(key, dict(case=case, releases=[]))['releases'].append(source)
    outside = []
    for source, report in reports:
        if report['rtl_modified'] or report['board_reset']:
            raise ValueError('Not an unchanged-image board report')
        cases = {c['name']: c for c in report['inputs']['cases']}
        if len(cases) != len(report['inputs']['cases']):
            raise ValueError('Duplicate report input case')
        seen = set()
        for result in report['results']:
            name = result['name']
            if name not in cases or name in seen:
                raise ValueError('Unexpected or repeated result within one report')
            seen.add(name)
            case = cases[name]
            key = (name, case['sha256'])
            status = result['status']
            if status not in ('passed', 'failed', 'stalled', 'incomplete', 'running'):
                raise ValueError('Unknown board status')
            if status == 'passed':
                lines = [line for line in result.get('output', '').splitlines()
                         if line.startswith(case['pass_marker'])]
                if (result.get('exit_code') != 0 or len(lines) != 1 or
                        not re.search(r'\bcases=[1-9]\d*\b', lines[0])):
                    raise ValueError('Missing unique numerical pass: '+name)
            if key not in catalog:
                outside.append(dict(name=name, sha256=key[1], status=status, report=source))
                continue
            if catalog[key]['case']['pass_marker'] != case['pass_marker']:
                raise ValueError('Board/release pass markers differ')
            failed_marker=case['pass_marker'][:-4]+'FAIL' if case['pass_marker'].endswith('PASS') else None
            if status=='passed' or (status=='failed' and failed_marker and any(
                    line.startswith(failed_marker) and re.search(r'\bcases=[1-9]\d*\b',line)
                    for line in result.get('output','').splitlines())):
                numerical_results.add(key)
            evidence.setdefault(key, {}).setdefault(status, set()).add(source)
    rows = []
    for key, entry in catalog.items():
        observed = evidence.get(key, {})
        terminal = set(observed)-{'running'}
        # A later pass must not erase a captured failure or incomplete/stalled attempt.
        if len(terminal) > 1:
            status = 'mixed_outcomes'
        elif terminal:
            status = next(iter(terminal))
        elif 'running' in observed:
            status = 'running'
        else:
            status = 'not_attempted'
        rows.append(dict(name=key[0], sha256=key[1], status=status,
                         releases=entry['releases'],
                         evidence={s:sorted(paths) for s,paths in observed.items()}))
    counts = dict(Counter(row['status'] for row in rows))
    return dict(scope='Selected release ELF execution inventory; not exhaustive ISA acceptance',
                planned=len(rows), counts=counts, cases=rows,
                elves_with_completed_numerical_result=len(numerical_results),
                historical_incomplete_with_completed_result=sum(
                    'incomplete' in row['evidence'] and
                    (row['name'],row['sha256']) in numerical_results for row in rows),
                outside_selected_releases=outside,
                all_selected_elves_finished=not any(counts.get(s, 0) for s in
                    ('not_attempted', 'running', 'incomplete', 'stalled', 'mixed_outcomes')))
