#!/usr/bin/env python3
"""Replay unchanged historical ports and independent probes on a sealed image."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
from prepare_build import INTEGRATION, PINS, sha


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--image', type=Path, required=True)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--include-matrix', action='store_true')
    args = cli.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('owned output only')
    if sha(INTEGRATION / 'run.py') != PINS['run.py']:
        raise ValueError('checked runner drift')
    out.mkdir(parents=True, exist_ok=False)
    cases = [('soc', n) for n in ('active_snan', 'no_snan', 'all_off', 'tail_vl15', 'prestart_snan')]
    cases += [('soc_matrix', 'prefix_quiet_tail')]
    if args.include_matrix:
        cases += [('soc_matrix', 'matrix_e' + str(sew)) for sew in (16, 32, 64)]
    results = []
    for programs, name in cases:
        command = [sys.executable, '-B', str(INTEGRATION / 'run.py'), 'run',
                   '--image', str(args.image.resolve()), '--programs', str(HERE / programs),
                   '--out', str(out / name), '--case', name, '--jobs', '1', '--timeout', '120', '--execute']
        with (out / (name + '.runner.log')).open('w') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        results.append(dict(case=name, command=command, returncode=process.returncode))
        (out / 'replay.json').write_text(json.dumps(dict(
            scope='selected archived-assembly/reconstructed-oracle ports plus independent probes; NOT full-original replay',
            results=results), indent=2) + '\n')
        if process.returncode:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
