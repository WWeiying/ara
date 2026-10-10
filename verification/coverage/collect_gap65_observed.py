#!/usr/bin/env python3
"""Report-only gap65 admission, DVE export, and finalization in order."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'verification/out/gap65-late-fault-runtime-20261004-02'
FINALIZER = ROOT / 'verification/coverage/finalize_gap65_observed.py'
STATUS = OUTPUT / 'validation.json'


def status(state, phase, **extra):
    STATUS.write_text(json.dumps(dict(status=state, phase=phase,
        baseline_passed=650, **extra), indent=2) + '\n')
    print(state + ': ' + phase, flush=True)


def run(command, label, timeout, environment=None):
    status('RUNNING', label)
    with (OUTPUT / (label + '.log')).open('x') as log:
        subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                       stderr=subprocess.STDOUT, timeout=timeout, check=True)


def main():
    if STATUS.exists():
        raise RuntimeError('existing collection status; do not overwrite or retry')
    try:
        run([sys.executable, '-B', str(FINALIZER), '--prepare'], 'admission', 600)
        plan = json.loads((OUTPUT / 'plan.json').read_text())
        env = dict(os.environ, DVE_WAIVERS='auto',
                   DVE_COVERAGE_TIMEOUT=str(plan['dve_timeout_s']))
        run(['bash', str(ROOT / 'verification/coverage/run_dve_coverage.sh'),
             str(OUTPUT / 'combined-dve'), '--inputs-file',
             str(OUTPUT / 'gap65-report-inputs.txt')], 'dve',
            plan['dve_outer_timeout_s'], env)
        run([sys.executable, '-B', str(FINALIZER), '--finalize'], 'finalization', 600)
        completion = json.loads((OUTPUT / 'gap65-complete-checkpoint.json').read_text())
        if completion.get('coverage_status') != 'COMPLETE' or completion.get('aggregate_passed') != 651:
            raise RuntimeError('incomplete final coverage proof')
        status('PASS', 'complete', coverage_status='COMPLETE', aggregate_passed=651)
        return 0
    except Exception as error:
        status('REJECTED', 'stopped', reason=str(error), coverage_status='NOT_ADMITTED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
