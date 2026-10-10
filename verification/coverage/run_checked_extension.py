#!/usr/bin/env python3
"""Checked thin adapter for run_targeted_extension; --prepare never launches VCS.

Existing selection fields are unchanged. Optional case.precheck declares
{format, record, source_hashes?, log?}; see coverage_evidence for native formats.
Prepare emits checked-preflight.json with the resolved per-case schema and pins
all checked baseline reports, ledgers, producer plans and independent evidence.
Use a fresh output directory after any preflight failure; no in-place retry.
"""
import argparse
import os
from pathlib import Path
import subprocess

import run_targeted_extension as base
import coverage_evidence as evidence

full = base.full
SCRIPT = Path(__file__).resolve()
VERSION = 'checked-extension-v1'


def failure(output, phase, error):
    output.mkdir(parents=True, exist_ok=True)
    full.save(output / 'checked-failure.json', {'status': 'REJECTED', 'phase': phase,
        'reason': f'{type(error).__name__}: {error}', 'launch_attempted': False})
    checkpoint = output / 'checkpoint.json'
    state = full.read(checkpoint) if checkpoint.exists() else {'simulations_started': False, 'cases': {}}
    state.update(status='PREFLIGHT_FAILED', phase=phase)
    full.save(checkpoint, state)


def frozen(output, case=None, all_cases=False):
    plan = full.frozen(output, case, all_cases)
    full.require(plan.get('checked_extension') == VERSION, 'plan lacks checked admission')
    full.require(not (output / 'checked-failure.json').exists(), 'checked plan was rejected')
    # Batch boundaries and launch use all_cases; workers retain the old bounded
    # critical-file checks instead of rehashing the entire historical corpus.
    return plan


def prepare(output, selection):
    full.require(not output.exists(), 'new output directory required')
    try:
        checked, rows, cases = evidence.validate(selection)
        base.prepare(output, selection)
        full.require(full.read(output / 'inputs/baseline-ledger.json') == rows,
                     'baseline changed between admission and prepare')
        plan = full.read(output / 'plan.json')
        full.require({c['source_name']: c['elf_sha256'] for c in plan['cases']} ==
                     {c['name']: c['elf_sha256'] for c in cases}, 'new ELF changed during prepare')
        checked.pin(SCRIPT)
        checked.pin(Path(evidence.__file__))
        checked.pin(Path(base.__file__))
        for path, digest in checked.files.items():
            full.require(path not in plan['files'] or plan['files'][path] == digest,
                         f'pin changed during prepare: {path}')
        full.check(checked.files)
        report = output / 'checked-preflight.json'
        full.save(report, {'status': 'PASS', 'schema': VERSION, 'selection': str(selection),
            'baseline_passed': len(rows), 'cases': cases, 'simulations_started': False,
            'checked_files': checked.files})
        plan['files'].update(checked.files)
        plan['files'].update(full.pins([report]))
        plan['checked_extension'] = VERSION
        full.save(output / 'plan.json', plan)
        full.save(output / 'plan.sha256.json', full.pins([output / 'plan.json']))
        frozen(output, all_cases=True)
        print(f'CHECKED PREPARED: {len(cases)} new cases, {len(rows)} independent baseline PASS; no launch',
              flush=True)
    except Exception as error:
        failure(output, 'checked prepare', error)
        raise


def summarize(output, plan):
    current = frozen(output, all_cases=True)
    full.require(current == plan, 'summarize plan differs')
    # Apply the same independent-admission rules to newly produced PASS rows.
    checked = evidence.Evidence()
    checked.plans[output.resolve()] = plan
    checked.collections[output.resolve()] = {}
    for case in plan['cases']:
        row = full.read(output / 'outcomes' / (case['name'] + '.json'))
        if row['status'] == 'PASS':
            checked.baseline_row(row, plan['image'], plan['simv'])
    result = base.summarize(output, plan)
    frozen(output, all_cases=True)
    return result


def launch(output):
    try:
        plan = frozen(output, all_cases=True)
    except Exception as error:
        failure(output, 'checked launch', error)
        raise
    command = full.systemd_command(output, plan)
    command[command.index(str(full.SCRIPT))] = str(SCRIPT)
    return subprocess.call(command)


def install_hooks():
    full.batch.SCRIPT, full.batch.frozen = SCRIPT, frozen
    full.batch.commands, full.batch.summarize = full.commands, summarize
    full.batch.schedule = full.original_schedule


def main():
    install_hooks()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    for flag in ('prepare', 'launch', 'execute'):
        modes.add_argument('--' + flag, action='store_true')
    modes.add_argument('--worker')
    modes.add_argument('--directed')
    args = parser.parse_args()
    output = full.base.checked_output(args.output)
    os.environ['PYTHONPATH'] = str(full.ROOT / 'verification')
    if args.prepare:
        full.require(args.selection is not None, '--selection required')
        prepare(output, args.selection.resolve(strict=True))
        return 0
    if args.launch:
        return launch(output)
    plan = frozen(output, all_cases=args.execute)
    full.require(os.environ.get('ARA_CHECKPOINT_UNIT') == plan['service'] and os.environ.get('INVOCATION_ID'),
                 'registered systemd service required')
    if args.worker:
        return full.worker(output, args.worker)
    if args.directed:
        return full.batch.directed(output, args.directed)
    return base.execute(output)


if __name__ == '__main__':
    raise SystemExit(main())
