#!/usr/bin/env python3
"""Match complete production SoC suites by exact cycle-window line labels."""
import argparse
import hashlib
import json
from pathlib import Path
import re

CYCLE = re.compile(r'\[PERF\] total_cycles\s*:\s*(\d+)|(?<![\w])cycles=(\d+)')
ERROR = re.compile(r'^.*(?:Fatal:|Error:|FAILED|\bFAIL\b|started at .*failed at|watchdog_timeout: 1).*$', re.M)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory):
    execution = directory.parent/'execution.json'
    if execution.exists():
        assert json.loads(execution.read_text())['state'] == 'COMPLETE', str(execution)
    regression = directory/'regression'
    manifest = json.loads((regression/'manifest.json').read_text())
    assert manifest['state'] == 'COMPLETE', str(regression)
    assert sha(Path(manifest['simulator'])) == manifest['simulator_sha256']
    tests = manifest['tests']
    assert len(tests) == 50 and len({t['app'] for t in tests}) == 50
    assert all(t['pass'] for t in tests)
    assert {p.name for p in (regression/'inputs').iterdir() if p.is_file()} == {t['app'] for t in tests}
    result = {}
    for test in tests:
        app = test['app']
        assert sha(regression/'inputs'/app) == test['elf_sha256'], app
        log = (regression/app/'stdout.log').read_text()
        assert 'Core Test *** SUCCESS *** (tohost = 0)' in log and not ERROR.search(log), app
        windows = {}
        for line in log.splitlines():
            matches = list(CYCLE.finditer(line))
            if not matches:
                continue
            assert len(matches) == 1, ('multiple cycle fields on one line', app, line)
            match = matches[0]
            group = 1 if match.group(1) is not None else 2
            start, end = match.span(group)
            label = line[:start]+'<cycles>'+line[end:]
            assert label not in windows, ('duplicate cycle-window label', app, label)
            windows[label] = {'cycles': int(match.group(group)), 'line': line}
        finish = re.search(r'\$finish at simulation time\s+(\d+)', log)
        assert finish, app
        result[app] = {'elf_sha256': test['elf_sha256'], 'windows': windows,
                       'finish_time_ticks': int(finish.group(1))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'shared', 'timing', 'seed-stage'):
        parser.add_argument('--'+name, type=Path, required=True, help='Directory containing regression/')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    directories = {name: getattr(args, name.replace('-', '_')).resolve()
                   for name in ('baseline', 'shared', 'timing', 'seed-stage')}
    suites = {name: load(path) for name, path in directories.items()}
    baseline = suites['baseline']
    assert all(set(suite) == set(baseline) for suite in suites.values())
    rows, problems, finishes = [], [], []
    for app, original in baseline.items():
        labels = list(original['windows'])
        for name, suite in suites.items():
            assert suite[app]['elf_sha256'] == original['elf_sha256'], (app, name)
            actual = list(suite[app]['windows'])
            if set(actual) != set(labels):
                problems.append({'app': app, 'mode': name,
                    'missing_labels': sorted(set(labels)-set(actual)),
                    'additional_labels': sorted(set(actual)-set(labels))})
            elif actual != labels:
                problems.append({'app': app, 'mode': name, 'window_order_changed': True})
        for label in labels:
            values = {name: suite[app]['windows'].get(label) for name, suite in suites.items()}
            cycles = {name: value['cycles'] if value is not None else None for name, value in values.items()}
            base = cycles['baseline']
            deltas = {name: value-base if value is not None else None for name, value in cycles.items()}
            percentages = {name: 100*delta/base if delta is not None and base else None
                           for name, delta in deltas.items()}
            rows.append({'app': app, 'label': label, 'cycles': cycles, 'cycle_deltas': deltas,
                         'percent_changes': percentages,
                         'original_lines': {name: value['line'] if value else None for name, value in values.items()}})
        ticks = {name: suite[app]['finish_time_ticks'] for name, suite in suites.items()}
        finishes.append({'app': app, 'finish_time_ticks': ticks,
                         'delta_ticks': {name: value-ticks['baseline'] for name, value in ticks.items()}})
    assert len(rows) == 105, f'Expected 105 baseline windows, got {len(rows)}'
    summary = {}
    for name in ('shared', 'timing', 'seed-stage'):
        matched = [row for row in rows if row['cycle_deltas'][name] is not None]
        worst = max(matched, key=lambda row: row['percent_changes'][name])
        summary[name] = {'functional_pass': 50, 'window_count': len(matched),
            'unchanged': sum(row['cycle_deltas'][name] == 0 for row in matched),
            'increased': sum(row['cycle_deltas'][name] > 0 for row in matched),
            'decreased': sum(row['cycle_deltas'][name] < 0 for row in matched),
            'max_relative_regression_percent': max(0, worst['percent_changes'][name]),
            'worst_window': {'app': worst['app'], 'label': worst['label'],
                             'baseline_cycles': worst['cycles']['baseline'],
                             'candidate_cycles': worst['cycles'][name]}}
    report = {'directories': {name: str(path) for name, path in directories.items()},
              'label_policy': 'Only the matched cycle digit span is replaced. All other characters, including every other numeric field, must match exactly. Order changes are also reported as mismatches.',
              'functional_all_pass': True, 'labels_all_match': not problems,
              'label_mismatches': problems, 'summary': summary,
              'windows': rows, 'finish_times': finishes}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    table = ['| App | Window label | Baseline | Shared | Timing | Seed stage | Shared % | Timing % | Seed stage % |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        values = [row['cycles'][name] for name in directories]
        percentages = [row['percent_changes'][name] for name in ('shared', 'timing', 'seed-stage')]
        table.append('| '+row['app']+' | '+row['label'].replace('|', '\\|')+' | '+
                     ' | '.join(str(value) for value in values)+' | '+
                     ' | '.join(f'{value:+.3f}%' if value is not None else 'MISMATCH' for value in percentages)+' |')
    (args.out/'windows.md').write_text('\n'.join(table)+'\n')
    print(json.dumps({'labels_all_match': not problems, 'summary': summary}, indent=2))
    raise SystemExit(0 if not problems else 1)


if __name__ == '__main__':
    main()
