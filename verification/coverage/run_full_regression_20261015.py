#!/usr/bin/env python3
"""Fresh RTL replay of the historical 600 core and 198 extension stimuli.

Historical verdicts select inputs only. Existing core simulation and independent
checkers remain intact; functional failures do not prevent other tests running.
"""
import argparse
import copy
import os
from pathlib import Path
import subprocess
import sys
import time

import run_full_recollection_20260928 as core
import reviewed_wall_budgets as budgets

ROOT = core.ROOT
SCRIPT = Path(__file__).resolve()
HISTORY = ROOT / 'verification/out/repaired-aligned-600-20260930-01/plan.json'
LEDGER = ROOT / ('verification/out/gather-war-offline-admitted798-v2-parent-20261008-01/'
                 'elf-ledger-dedup.json')
BUILD = ROOT / 'verification/out/full-regression-build-20261015-01'
OUTPUT = ROOT / 'verification/out/full-regression-20261015-01'
REPAIR = ROOT / 'verification/out/wt-inval-collision-20261015-01/summary.json'
EXTENSIONS = SCRIPT.with_name('replay_historical_extensions_20261015.py')


def inventory(selection=None):
    previous = core.read(HISTORY)
    ledger = core.read(LEDGER)
    core.require(ledger['ledger_members'] == len(ledger['members']) == 798,
                 'expected complete 798-member historical selection')
    core.require(len(previous['cases']) == 600, 'expected historical 600 core cases')
    ledger_hashes = [{*m['ELF_candidates'].values()} for m in ledger['members'][:600]]
    core.require(all(len(h) == 1 for h in ledger_hashes), 'ambiguous historical ELF')
    core.require({c['elf_sha256'] for c in previous['cases']} ==
                 {next(iter(h)) for h in ledger_hashes}, 'core/798 membership mismatch')
    cases = copy.deepcopy(previous['cases'])
    provenance = core.pins([HISTORY, LEDGER, SCRIPT])
    for case in cases:
        elf = Path(case['frozen_elf'])
        core.check({str(elf): case['elf_sha256']})
        case['source_elf'] = str(elf)
        case['source_files'] = {str(elf): case['elf_sha256']}
        if case.get('fault_vstart_probe'):
            case['source_files'].update(core.pins([Path(case['diagnostic_probe'])]))
    cases, evidence = budgets.apply(cases)
    provenance.update(evidence)
    selected = {k: copy.deepcopy(previous[k]) for k in (
        'aliases', 'source_counts', 'source_entries', 'unique_cases',
        'latest_entries', 'historical_additions', 'repair_smoke_entries',
        'excluded_static', 'gate_cases', 'gate_expected_count', 'gate_policy')}
    selected.update(cases=cases, files=provenance,
                    case_bounds={c['name']: dict(rtl_wall_s=c['timeout_s'],
                        runner_outer_s=c['timeout_s'] + 600, independent_audit_s=300)
                        for c in cases})
    return selected


def schedule_all(output, names, jobs):
    core.require(jobs == 8, 'reviewed full replay uses eight workers')
    core.save(output / 'dispatch-policy.json', dict(
        policy='CONTINUE_FUNCTIONAL_FAILURE_STOP_INFRASTRUCTURE',
        total=len(names), workers=jobs, retry=False,
        original_oracles_unchanged=True, gate_barrier=False))
    return core.original_schedule(output, names, jobs)


def launch_pipeline():
    core.base.check_service()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    state_path = OUTPUT / 'progress.json'
    state = dict(status='WAITING_FOR_BUILD', total=798, workers=8,
                 core_total=600, extension_total=198, build=str(BUILD),
                 historical_results_reused=False)
    core.save(state_path, state)
    try:
        deadline = time.monotonic() + 7500
        while True:
            status_path = BUILD / 'build-status.json'
            status = core.read(status_path) if status_path.exists() else {}
            if status.get('status') == 'PASS':
                break
            core.require(status.get('status') != 'FAIL', 'fresh build failed: ' + str(status))
            core.require(time.monotonic() < deadline, 'fresh build wait exceeded bound')
            time.sleep(30)
        core.require(core.read(REPAIR)['status'] == 'PASS_BASELINE_REPRODUCED_AND_REPAIRED',
                     'focused WT repair acceptance missing')
        files = core.read(BUILD / 'build-source-pins.json')
        files.update(core.pins([BUILD / 'build-status.json', REPAIR, SCRIPT]))
        freeze = OUTPUT / 'freeze.json'
        core.save(freeze, dict(status='READY_FOR_FULL_RECOLLECTION',
            simv=str(BUILD / 'sim/simv'), image=status['image'], files=files,
            repair_evidence=[str(REPAIR)]))
        core_output = OUTPUT / 'full-regression-core-20261015-01'
        core.prepare(core_output, core.DEFAULT_PLAN, freeze)
        state.update(status='RUNNING_CORE', core=str(core_output))
        core.save(state_path, state)
        # The existing worker validates every fresh verdict and VDB independently.
        rc = core.execute(core_output)
        checkpoint = core.read(core_output / 'checkpoint.json')
        state.update(core_returncode=rc, core_status=checkpoint['status'])
        core.require(checkpoint['status'] in ('PASS', 'COMPLETE_WITH_FAILURES'),
                     'core stopped on infrastructure error: ' + str(checkpoint.get('reason')))
        core.require(EXTENSIONS.is_file(), 'extension runner has not been installed')
        state.update(status='RUNNING_EXTENSIONS', extensions=str(OUTPUT / 'extensions'))
        core.save(state_path, state)
        command = [sys.executable, str(EXTENSIONS), '--simv', str(BUILD / 'sim/simv'),
                   '--output', str(OUTPUT / 'extensions'), '--jobs', '8']
        core.save(OUTPUT / 'extensions.command.json', dict(command=command))
        with (OUTPUT / 'extensions.log').open('x') as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        state.update(status='COMPLETE' if rc == result.returncode == 0 else 'COMPLETE_WITH_FAILURES',
                     extension_returncode=result.returncode)
        core.save(state_path, state)
        return 0 if state['status'] == 'COMPLETE' else 1
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        core.save(state_path, state)
        raise


def main():
    core.SCRIPT = SCRIPT
    core.inventory = inventory
    core.schedule = schedule_all
    core.batch.SCRIPT = SCRIPT
    core.batch.frozen = core.frozen
    core.batch.commands = core.commands
    core.batch.summarize = core.summarize
    core.batch.schedule = schedule_all
    if '--pipeline' in sys.argv:
        return launch_pipeline()
    if '--inventory-only' in sys.argv:
        import json
        selected = inventory()
        print(json.dumps(dict(core=len(selected['cases']), extensions=198, total=798,
                              kinds=dict(core.Counter(c['kind'] for c in selected['cases'])))))
        return 0
    return core.main()


if __name__ == '__main__':
    raise SystemExit(main())
