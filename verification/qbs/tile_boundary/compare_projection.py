#!/usr/bin/env python3
"""Compare accepted same-ELF projection runs, without mixing software variants."""
import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare(old, new, old_build, new_build):
    for run, build in ((old, old_build), (new, new_build)):
        require(run.get('state') == 'PASS' and run.get('post_pins_match') is True
                and run.get('performance_measured') is True, 'Unaccepted execution')
        require(build.get('state') == 'CANONICAL_SOC_BUILT_NOT_EXECUTED' and
                build.get('post_pins_match') is True, 'Unaccepted image build')
        require(run['image_pins'] == build['image_pins'], 'Run/image mismatch')
        measured = run['measured']
        require(measured['state'] == 'PASS' and measured['traffic'] ==
                dict(commands=256, result_bytes=131072), 'Incomplete projection work')
        require(len(measured['trials']) == 4, 'Missing ABBA trials')
    require(old['elf_sha256'] == new['elf_sha256'], 'Different program binaries')
    require(old_build['config'] == new_build['config'], 'Different hardware configuration')
    old_rows, new_rows = old['measured']['trials'], new['measured']['trials']
    for index, (a, b) in enumerate(zip(old_rows, new_rows)):
        for key in ('id', 'candidate', 'hits', 'misses', 'stores', 'fcsr', 'vcsr', 'errors'):
            require(a[key] == b[key], 'Software/state mismatch: ' + key)
        require(a['id'] == index and a['candidate'] == int(index in (1, 2))
                and a['errors'] == 0, 'Wrong software order or failed trial')
        for row in (a, b):
            require(all(row[k] > 0 for k in ('total', 'prep', 'execute')), 'Invalid cycles')
    variants = {}
    for name, ids in (('original_sums', (0, 3)), ('parallel_sums', (1, 2))):
        phases = {}
        for phase in ('total', 'prep', 'execute'):
            a = sum(old_rows[i][phase] for i in ids)
            b = sum(new_rows[i][phase] for i in ids)
            phases[phase] = dict(baseline_mean=a/2, candidate_mean=b/2,
                                 speedup=a/b, cycle_reduction=1-b/a)
        variants[name] = phases
    return dict(state='PAIRED_ACCEPTED_RECORDS_COMPARED', variants=variants,
                whole_model_speedup=False, functional_tests_rerun_by_this_tool=False)


def load(path):
    return json.loads(path.read_text())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-run', 'candidate-run', 'baseline-build', 'candidate-build'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    paths = [args.baseline_run, args.candidate_run, args.baseline_build, args.candidate_build]
    result = compare(*(load(p) for p in paths))
    result['record_sha256'] = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in paths}
    print(json.dumps(result, indent=2))
