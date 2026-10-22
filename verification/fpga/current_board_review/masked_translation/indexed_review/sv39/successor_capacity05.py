#!/usr/bin/env python3
"""Two-worker successor; external simulations count toward the eight-slot gate."""
import argparse
import copy
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import successor_snapshot03 as snapshot
gate = snapshot.gate
HERE = snapshot.HERE
OUT = HERE / 'vcs_plan05'
ORIGINAL_VALIDATE = gate.old.validate_plan


def validate(plan):
    gate.require(plan['max_jobs'] == 2 and plan['suggested_service_runtime_s'] == 33600,
                 'Fixed two-job/12-wave service budget differs')
    inherited = {**plan, 'max_jobs': 4}
    ORIGINAL_VALIDATE(inherited)


def decide(nf2, arithmetic, processes, jobs):
    gate.require(jobs == 2, 'NF7 requires exactly two workers')
    for state in (nf2, arithmetic):
        gate.require(state.get('LoadState') in ('loaded', 'not-found') and
                     state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0',
                     'Own NF2/arithmetic must be terminal, including GC')
        if state['LoadState'] == 'not-found':
            gate.require(not state.get('ControlGroup'), 'Unknown active unit refused')
    for p in processes:
        normalized = {**p, 'argv': [a.split('=', 1)[1] if a.startswith('--') and '=' in a else a
                                    for a in p['argv']]}
        gate.require(not gate.owner(normalized, gate.NF2_UNIT, gate.NF2.parent) and
                     not gate.owner(normalized, gate.ARITH_UNIT, gate.ARITH),
                     'Own NF2/arithmetic residual owner refused')
    external = [p for p in processes if Path(p['exe']).name == 'simv']
    gate.require(len(external) + jobs <= 8, 'External live simv plus two NF7 reservations exceeds eight')
    return dict(nf2=nf2, arithmetic=arithmetic, external_simvs=external,
                external_live_count=len(external), nf7_jobs=2, total_at_admission=len(external)+2,
                ownership_snapshot=processes, no_polling=True, external_processes_untouched=True)


def capacity_gate(plan, image, jobs):
    # Full completion evidence is pinned during preparation and verified again
    # here; only then take the single live admission snapshot.
    gate.old.verify(plan['nf2_terminal_pins'])
    gate.old.verify(plan['arithmetic_terminal_pins'])
    nf2 = gate.unit_state(gate.NF2_UNIT)
    arithmetic = gate.unit_state(gate.ARITH_UNIT)
    processes = snapshot.process_snapshot()
    try:
        result = decide(nf2, arithmetic, processes, jobs)
    except Exception as error:
        gate.save(OUT / 'admission.json', dict(status='REFUSED_NO_NF7_LAUNCH', error=repr(error),
            nf2=nf2, arithmetic=arithmetic, processes=processes, PAM=snapshot.AUDIT,
            captured_unix=time.time()))
        raise
    result['terminal_pins'] = plan['arithmetic_terminal_pins']
    gate.save(OUT / 'admission.json', dict(status='PASS_TWO_NF7_RESERVED',
        gate=result, PAM=snapshot.AUDIT, captured_unix=time.time()))
    return result


def preflight():
    gate.require(not OUT.exists(), 'Fresh output required')
    gate.require(gate.sha(snapshot.PREVIOUS / 'plan.json') == snapshot.PREVIOUS_SHA, 'Plan02 changed')
    plan = copy.deepcopy(gate.read(snapshot.PREVIOUS / 'plan.json'))
    ORIGINAL_VALIDATE(plan)
    gate.old.verify(plan['pins'])
    for name in ('snapshot03_host_tests.json', 'capacity05_host_tests.json'):
        host = gate.read(HERE / name)
        gate.require(host['status'] in ('HOST_SNAPSHOT03_PASS_NOT_DUT', 'HOST_CAPACITY05_PASS_NOT_DUT'),
                     'Missing host verification')
        gate.old.verify(host['pins'])
    su = gate.accepted_helpers()
    image = su.check_image()
    su.parent_gate(image)
    gate.require(image['files'] == plan['image_files'], 'Image changed')
    arithmetic = gate.arithmetic_evidence(image)
    OUT.mkdir()
    for name in ('programs', 'ledgers', 'groups'):
        (OUT / name).mkdir()
    names = ['programs/programs.json', 'reference_acceptance.json']
    names += [f'ledgers/g{g:02d}.json' for g in gate.old.GROUPS]
    for name in names:
        gate.save(OUT / name, gate.read(snapshot.PREVIOUS / name))
        gate.require(gate.sha(OUT / name) == gate.sha(snapshot.PREVIOUS / name), 'Accepted input changed')
    command = gate.old.command(OUT)
    command[command.index('--jobs')+1] = '2'
    gate.save(OUT / 'dryrun_command.json', command)
    with (OUT / 'dryrun.log').open('x') as log:
        subprocess.run(command, cwd=gate.old.ref.base.ROOT, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    rows = gate.read(OUT / 'dryrun/summary.json')
    gate.require(len(rows) == 24 and {x['name'] for x in rows} == {f'nf7_g{g:02d}' for g in gate.old.GROUPS}
                 and all(x['status'] == 'DRY_RUN' for x in rows), 'Dry-run differs')
    plan.update(max_jobs=2, suggested_service_runtime_s=33600,
        predecessor_plan=str(snapshot.PREVIOUS / 'plan.json'), predecessor_sha256=snapshot.PREVIOUS_SHA,
        arithmetic_terminal_pins=arithmetic,
        delta='Exactly two NF7 workers; terminal own suites; external live simv + 2 <= 8; outer 33600s')
    paths = [Path(__file__), Path(snapshot.__file__), HERE / 'test_capacity05.py',
        HERE / 'capacity05_host_tests.json', HERE / 'snapshot03_host_tests.json',
        snapshot.PREVIOUS / 'plan.json', OUT / 'dryrun_command.json', OUT / 'dryrun/summary.json',
        *[OUT / n for n in names]]
    plan['pins'].update(arithmetic)
    plan['pins'].update(gate.pins(paths))
    validate(plan)
    gate.old.verify(plan['pins'])
    gate.require(su.check_image() == image, 'Post-preflight image changed')
    gate.save(OUT / 'plan.json', plan)
    gate.save(OUT / 'preflight.json', dict(status='CAPACITY05_PREFLIGHT_PASS_NOT_LAUNCHED',
        plan_sha256=gate.sha(OUT / 'plan.json'), jobs=2, group_timeout_s=2400,
        group_outer_s=2700, service_outer_s=33600, VCS_started=False,
        single_actual_admission_deferred_to_worker=True))
    print('CAPACITY05_PREFLIGHT_PASS_NOT_LAUNCHED', gate.sha(OUT / 'plan.json'), flush=True)


def configure():
    gate.OUT = OUT
    gate.capacity_gate = capacity_gate
    gate.old.validate_plan = validate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'worker'))
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if args.action == 'preflight':
        preflight()
    else:
        configure()
        try:
            gate.require(args.jobs == 2, 'Only two workers authorized')
            sys.exit(gate.worker(args.authorize_run, args.approved_plan_sha256, args.jobs))
        except Exception as error:
            if OUT.is_dir():
                gate.save(OUT / f'gate_refusal_{time.time_ns()}.json', dict(error=repr(error),
                    status='REFUSED_OR_ERROR_NOT_PASS', worker_record_exists=(OUT / 'worker.json').exists()))
            raise
