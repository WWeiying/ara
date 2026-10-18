#!/usr/bin/env python3
"""Validate the full 72-window exact-family/representation tradeoff matrix."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
from run_reduction_audit import classify
from run_exact_backend_tradeoff import exact_off_define


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    a = p.parse_args()
    config = json.loads((a.root / 'configuration.json').read_text())
    for record in config['sources'].values():
        assert sha(Path(record['snapshot'])) == record['sha256'], 'Frozen RTL/header changed'
    modes = ['full', 'banked', 'exact_off']
    defines = [set(config['modes'][m]['defines']) for m in modes]
    assert defines[0] - defines[1] == {'+define+ARA_RED_EXACT_SEGMENTED_4LANE=1'} and not defines[1] - defines[0]
    assert defines[2] == {s for s in defines[0] if not exact_off_define(s)}
    expected = set(itertools.product([16, 32], [1, 4, 8, 32, 128, 256], [0, 1, 2], [0, 1]))
    windows, evidence = {}, []
    app = config['apps'][0]
    for mode in modes:
        directory = a.root / mode
        report = json.loads((directory / 'regression/manifest.json').read_text())
        assert report['state'] == 'COMPLETE' and report['expected_apps'] == [app]
        assert len(report['tests']) == 1 and report['tests'][0]['app'] == app
        test = report['tests'][0]
        assert test['elf_sha256'] == config['elf_sha256'] == sha(directory / 'regression/inputs' / app)
        assert report['simulator_sha256'] == sha(Path(report['simulator']))
        log = directory / 'regression' / app / 'stdout.log'
        text = log.read_text()
        checked = dict(test)
        classify(checked, text)
        assert checked['pass'] and test['pass'], mode + ': failing test'
        matches = re.findall(r'EXACT_TRADEOFF sew=(\d+) vl=(\d+) mask=(\d+) chain=(\d+) reductions=16 chain_span=(\d+) cycles=(\d+) PASS', text)
        for row in matches:
            sew, vl, mask, chain, span = map(int, row[:5])
            required_span = 8 if chain and sew == 16 and vl == 256 and mask == 0 else 16 if chain else 0
            assert span == required_span, 'Unexpected seed chain measurement'
        values = {tuple(map(int, row[:4])): int(row[5]) for row in matches}
        assert len(matches) == len(values) == 72 and set(values) == expected, mode + ': incomplete or duplicate windows'
        windows[mode] = values
        evidence.append({'mode': mode, 'manifest_sha256': sha(directory / 'regression/manifest.json'), 'log_sha256': sha(log)})
    rows = []
    for key in sorted(expected):
        cycles = {m: windows[m][key] for m in modes}
        rows.append(dict(zip(['sew', 'vl', 'mask', 'chain'], key), cycles=cycles,
                         exact_family_cycle_reduction_percent=100*(1-cycles['full']/cycles['exact_off']),
                         segmented_cycle_reduction_percent=100*(1-cycles['full']/cycles['banked'])))
    result = {'complete': True, 'elf_sha256': config['elf_sha256'], 'tests': rows, 'evidence': evidence,
              'scope': config['scope'],
              'limits': 'Exactly representable sums only; independent stream includes source writes; no general ISA, area, Fmax or workload-average claim'}
    (a.root / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    for row in rows:
        print(row['sew'], row['vl'], row['mask'], row['chain'], row['cycles'])


if __name__ == '__main__':
    main()
