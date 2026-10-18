#!/usr/bin/env python3
"""Compare strict cycle labels against a baseline and previous production version."""
import argparse
import json
from pathlib import Path
import re

from collect_production_shared_soc_comparison import CYCLE, ERROR, load, sha


def load_scope(directory, apps):
    if not apps:
        return load(directory)
    # Partial reporting is explicit: only completed requested tests are read;
    # the driver and full regression may still be running.
    regression = directory/'regression'
    manifest = json.loads((regression/'manifest.json').read_text())
    assert manifest['state'] in ('RUNNING', 'COMPLETE'), str(regression)
    assert sha(Path(manifest['simulator'])) == manifest['simulator_sha256']
    tests = {test['app']: test for test in manifest['tests']}
    assert set(apps) <= set(tests), ('Requested tests not complete yet', sorted(set(apps)-set(tests)))
    result = {}
    for app in apps:
        test = tests[app]
        assert test['pass'], app
        assert sha(regression/'inputs'/app) == test['elf_sha256'], app
        text = (regression/app/'stdout.log').read_text()
        assert 'Core Test *** SUCCESS *** (tohost = 0)' in text and not ERROR.search(text), app
        windows = {}
        for line in text.splitlines():
            matches = list(CYCLE.finditer(line))
            if not matches:
                continue
            assert len(matches) == 1, (app, 'multiple cycle fields', line)
            match = matches[0]
            group = 1 if match.group(1) is not None else 2
            start, end = match.span(group)
            label = line[:start]+'<cycles>'+line[end:]
            assert label not in windows, (app, 'duplicate cycle label', label)
            windows[label] = {'cycles':int(match.group(group)), 'line':line}
        finish = re.search(r'\$finish at simulation time\s+(\d+)', text)
        assert finish, app
        result[app] = {'elf_sha256':test['elf_sha256'], 'windows':windows,
                       'finish_time_ticks':int(finish.group(1))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for mode in ('baseline', 'previous', 'candidate'):
        parser.add_argument('--'+mode, type=Path, required=True, help='Directory containing regression/')
    parser.add_argument('--apps', nargs='+', help='Explicit partial scope; each selected test must already have passed')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert not args.apps or len(args.apps) == len(set(args.apps)), 'Duplicate app'
    directories = {mode:getattr(args, mode).resolve() for mode in ('baseline','previous','candidate')}
    suites = {mode:load_scope(directory,args.apps) for mode,directory in directories.items()}
    baseline = suites['baseline']
    assert all(set(suite) == set(baseline) for suite in suites.values())
    rows, problems, finishes = [], [], []
    for app, original in baseline.items():
        labels = list(original['windows'])
        for mode, suite in suites.items():
            assert suite[app]['elf_sha256'] == original['elf_sha256'], (app,mode,'ELF differs')
            actual = list(suite[app]['windows'])
            if actual != labels:
                problems.append({'app':app, 'mode':mode,
                    'missing_labels':sorted(set(labels)-set(actual)),
                    'additional_labels':sorted(set(actual)-set(labels)),
                    'order_changed':set(actual)==set(labels)})
        for label in labels:
            entries = {mode:suite[app]['windows'].get(label) for mode,suite in suites.items()}
            cycles = {mode:entry['cycles'] if entry else None for mode,entry in entries.items()}
            comparisons = {}
            for reference, target in (('baseline','candidate'),('previous','candidate'),('baseline','previous')):
                first, second = cycles[reference], cycles[target]
                assert first is None or first > 0, (app,label,reference,'nonpositive reference cycles')
                delta = second-first if first is not None and second is not None else None
                comparisons[reference+'_to_'+target] = {'delta':delta,
                    'percent':100*delta/first if delta is not None else None}
            rows.append({'app':app,'label':label,'cycles':cycles,'comparisons':comparisons,
                         'original_lines':{mode:entry['line'] if entry else None for mode,entry in entries.items()}})
        ticks = {mode:suite[app]['finish_time_ticks'] for mode,suite in suites.items()}
        finishes.append({'app':app,'finish_time_ticks':ticks,
            'candidate_minus_baseline_ticks':ticks['candidate']-ticks['baseline'],
            'candidate_minus_previous_ticks':ticks['candidate']-ticks['previous']})
    assert rows, 'No measured windows'
    if not args.apps:
        assert len(rows) == 105
    summary = {}
    for pair in ('baseline_to_candidate','previous_to_candidate','baseline_to_previous'):
        matched = [row for row in rows if row['comparisons'][pair]['delta'] is not None]
        worst = max(matched, key=lambda row:row['comparisons'][pair]['percent'])
        summary[pair] = {'window_count':len(matched),
            'unchanged':sum(row['comparisons'][pair]['delta']==0 for row in matched),
            'increased':sum(row['comparisons'][pair]['delta']>0 for row in matched),
            'decreased':sum(row['comparisons'][pair]['delta']<0 for row in matched),
            'max_relative_regression_percent':max(0,worst['comparisons'][pair]['percent']),
            'worst_window':{'app':worst['app'],'label':worst['label'],'cycles':worst['cycles']}}
    report = {'scope':'selected completed tests only' if args.apps else 'complete 50-test suite',
        'functional_pass_count':len(baseline),'labels_all_match':not problems,'label_mismatches':problems,
        'label_policy':'Only cycle digits replaced; all other characters/numbers and window ordering must match.',
        'directories':{mode:str(directory) for mode,directory in directories.items()},
        'summary':summary,'windows':rows,'finish_times':finishes}
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    table = ['| App | Window label | Baseline | Previous | Candidate | Change vs baseline | Change vs previous |',
             '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        cells = [str(row['cycles'][mode]) for mode in directories]
        for pair in ('baseline_to_candidate','previous_to_candidate'):
            result = row['comparisons'][pair]
            cells.append(f"{result['delta']:+d} ({result['percent']:+.3f}%)" if result['delta'] is not None else 'MISMATCH')
        table.append('| '+row['app']+' | '+row['label'].replace('|','\\|')+' | '+' | '.join(cells)+' |')
    (args.out/'windows.md').write_text('\n'.join(table)+'\n')
    print(json.dumps({key:report[key] for key in ('scope','functional_pass_count','labels_all_match','summary')},indent=2))
    raise SystemExit(0 if not problems else 1)


if __name__ == '__main__':
    main()
