#!/usr/bin/env python3
"""Wait for the frozen direct-read regression, then run the matched SoC pair.

Never re-run an attempted synthesis. A STOP file in --out prevents subsequent
launches; it does not kill an already running Design Compiler process.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--regression', type=Path, required=True)
    parser.add_argument('--regression-pid', type=int, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    regression = args.regression.resolve()
    root = Path(__file__).resolve().parents[3]
    here = Path(__file__).resolve().parent
    proc = Path('/proc') / str(args.regression_pid)
    command = (proc / 'cmdline').read_bytes()
    if b'run_exact_area_soc.py' not in command or regression.name.encode() not in command:
        raise ValueError('Regression process identity mismatch')
    identity = (proc / 'stat').read_text().split(') ', 1)[1].split()[19]
    frozen = {str(p): sha(p) for p in (
        regression / 'configuration.json',
        regression / 'integration_source_audit.json',
        args.reference.resolve() / 'manifest.json',
        args.candidate.resolve() / 'manifest.json',
        here / 'area_pair.py', here / 'flow.py',
        here / 'audit_area_timing_pair.py',
        root / 'hardware/scripts/compare_ordered_add_runs.py')}
    (out / 'inputs.json').write_text(json.dumps(frozen, indent=2) + '\n')

    def state(name, **kwargs):
        temp = out / 'status.tmp'
        temp.write_text(json.dumps({'state': name, 'time_unix': time.time(), **kwargs}, indent=2) + '\n')
        temp.replace(out / 'status.json')

    def check_inputs():
        if (out / 'STOP').exists():
            raise RuntimeError('STOP requested; no further launches')
        for path, digest in frozen.items():
            if sha(path) != digest:
                raise RuntimeError('Frozen input or runner changed: ' + path)

    def run(label, command):
        check_inputs()
        with (out / (label + '.log')).open('x') as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        while True:
            check_inputs()
            reports = []
            for mode in ('baseline', 'scalar'):
                try:
                    reports.append(json.loads((regression / mode / 'regression/manifest.json').read_text()))
                except (FileNotFoundError, json.JSONDecodeError):
                    reports.append({})
            if all(r.get('state') == 'COMPLETE' for r in reports):
                break
            if not proc.exists() or (proc / 'stat').read_text().split(') ', 1)[1].split()[19] != identity:
                raise RuntimeError('Original regression process exited before complete reports')
            state('WAITING_REGRESSION', completed=[len(r.get('tests', [])) for r in reports])
            time.sleep(30)
        run('cycle_comparison', [sys.executable, str(root / 'hardware/scripts/compare_ordered_add_runs.py'), str(regression)])
        comparison = json.loads((regression / 'comparison.json').read_text())
        if not comparison['all_pass'] or comparison['expected_test_count'] != 50:
            raise RuntimeError('Full 50-test performance gate failed')
        for mode in ('baseline', 'scalar'):
            manifest = json.loads((regression / mode / 'source_manifest.json').read_text())
            for path, digest in manifest['sources'].items():
                if sha(path) != digest:
                    raise RuntimeError('Simulation source changed: ' + path)
        integration = json.loads((regression / 'integration_source_audit.json').read_text())
        if not integration['all_current_ara_src_matched']:
            raise RuntimeError('Integration source audit not passed')
        for record in integration['modules']:
            if any(sha(path) != record['sha256'] for path in record['simulation_sources']):
                raise RuntimeError('Integration source evidence changed')
        run('input_audit', [sys.executable, str(here / 'audit_area_timing_pair.py'),
            str(args.reference.resolve()), str(args.candidate.resolve()), '--direct-read',
            '--out', str(out / 'input_audit.json')])
        for label, directory, profile in (
            ('reference', args.reference.resolve(), 'area_pair_timing'),
            ('candidate', args.candidate.resolve(), 'area_pair_direct_read')):
            check_inputs()
            if json.loads((directory / 'status.json').read_text())['state'] != 'PREPARED':
                raise RuntimeError('Synthesis already attempted: ' + str(directory))
            while True:
                check_inputs()
                available = next(int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
                if available >= 80 * 1024 * 1024:
                    break
                state('WAITING_MEMORY', next_run=label, available_kib=available)
                time.sleep(30)
            state('RUNNING', active=label)
            run(label, [sys.executable, str(here / 'area_pair.py'), 'run', '--profile', profile, '--out', str(directory)])
            if json.loads((directory / 'status.json').read_text())['state'] != 'COMPLETE':
                raise RuntimeError('Synthesis did not complete: ' + label)
        state('COMPLETE', comparison_sha256=sha(regression / 'comparison.json'))
    except Exception as exc:
        state('STOPPED', reason=str(exc))
        raise


if __name__ == '__main__':
    main()
