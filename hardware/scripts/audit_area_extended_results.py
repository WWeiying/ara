#!/usr/bin/env python3
"""Audit a complete paired suite, retaining historically reproduced failures as FAIL.

Historical manifests are explicit evidence, not a test waiver. Any new failure
or changed signature prevents acceptance; even unchanged failures remain failures.
"""
import argparse
import json
import re
from pathlib import Path
from run_reduction_audit import classify, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--history', type=Path, action='append', default=[])
    args = parser.parse_args()
    history = []
    for path in args.history:
        for test in json.loads(path.read_text())['tests']:
            if not test['pass']:
                history.append((test, str(path), sha256(path)))
    reports = []
    for mode in ['baseline', 'scalar']:
        folder = args.root / mode / 'regression'
        manifest = json.loads((folder / 'manifest.json').read_text())
        tests = {t['app']: t for t in manifest['tests']}
        inputs = {p.name for p in (folder / 'inputs').iterdir() if p.is_file()}
        assert inputs and len(tests) == len(manifest['tests']) and set(tests) == inputs
        assert set(manifest['expected_apps']) == inputs and manifest['state'] == 'COMPLETE'
        assert sha256(Path(manifest['simulator'])) == manifest['simulator_sha256']
        for name, test in tests.items():
            assert sha256(folder / 'inputs' / name) == test['elf_sha256']
            log = folder / name / 'stdout.log'
            checked = dict(test)
            classify(checked, log.read_text())
            assert checked['pass'] == test['pass'] and checked['failures'] == test['failures']
            test['log_sha256'] = sha256(log)
            text = log.read_text()
            finish = re.search(r'\$finish at simulation time\s+(\d+)', text)
            test['finish_ticks'] = int(finish[1]) if finish else None
            test['windows'] = [int(v) for pair in re.findall(
                r'\[PERF\] total_cycles\s*:\s*(\d+)|(?<![\w])cycles=(\d+)', text)
                for v in pair if v]
        reports.append(tests)
    assert reports[0].keys() == reports[1].keys()
    rows = []
    for name, first in reports[0].items():
        second = reports[1][name]
        assert first['elf_sha256'] == second['elf_sha256']
        row = {'app': name, 'elf_sha256': first['elf_sha256'],
               'log_sha256': [first['log_sha256'], second['log_sha256']],
               'pass': first['pass'] and second['pass']}
        if row['pass']:
            assert first['finish_ticks'] is not None and second['finish_ticks'] is not None
            assert len(first['windows']) == len(second['windows'])
            row.update(finish_ticks=[first['finish_ticks'], second['finish_ticks']],
                       windows=[first['windows'], second['windows']],
                       no_cycle_regression=second['finish_ticks'] <= first['finish_ticks'] and
                       all(y <= x for x, y in zip(first['windows'], second['windows'])))
        else:
            matches = [(p, h) for t, p, h in history
                       if t['app'] == name and t['elf_sha256'] == first['elf_sha256']
                       and not first['pass'] and not second['pass']
                       and t['failures'] == first['failures'] == second['failures']]
            row.update(failure_signature=[first['failures'], second['failures']],
                       inherited_failure=bool(matches), historical_evidence=matches)
        rows.append(row)
    result = {'complete_suite': True, 'tests': rows,
              'all_pass': all(r['pass'] for r in rows),
              'no_new_failures': all(r['pass'] or r['inherited_failure'] for r in rows),
              'passing_tests_no_cycle_regression': all(r.get('no_cycle_regression', True) for r in rows),
              'scope': 'Frozen matched simulations; inherited failures remain FAIL; no Fmax/area claim'}
    (args.root / 'extended_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'tests'}, indent=2))
    print('PASS:', sum(r['pass'] for r in rows), 'FAIL:', sum(not r['pass'] for r in rows))
    raise SystemExit(0 if result['no_new_failures'] and result['passing_tests_no_cycle_regression'] else 1)


if __name__ == '__main__':
    main()
