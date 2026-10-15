#!/usr/bin/env python3
"""Parent-authorized scheduling successor: 24 slots, 32 GiB free, NF7 two jobs."""
import argparse
import copy
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import successor_capacity05 as previous
gate = previous.gate
snapshot = previous.snapshot
HERE = previous.HERE
SOURCE = HERE / 'vcs_plan05'
SOURCE_SHA = '622c4663714eb5d1deb638da18522f063473b6f77c079626679ab16a429f3f0f'
OUT = HERE / 'vcs_plan06'
ALIAS_UNIT = 'ara-mask-alias-candidate02.service'
ALIAS_OUT = HERE.parents[2] / 'mask_alias_original/vcs_candidate02_01'
CONFIG = dict(total_live_reserved_cap=24, minimum_available_bytes=32*1024**3,
    nf7_jobs=2, alias_reserved=1, alias_unit=ALIAS_UNIT, alias_output=str(ALIAS_OUT),
    formula='other_external_live + max(alias_actual, 1) + 2 <= 24',
    authorization='Parent explicit scheduling update, resource check 23:55: 64 CPUs, 251 GiB total, 172 GiB available; do not modify external jobs',
    group_timeout_s=2400, group_outer_s=2700, service_outer_s=33600)


def validate(plan):
    previous.validate(plan)
    gate.require(plan['admission_config'] == CONFIG and
                 plan['pins'][str(OUT / 'admission_config.json')] == gate.sha(OUT / 'admission_config.json'),
                 'Reviewed scheduling configuration differs')


def decide(nf2, arithmetic, processes, jobs, available):
    gate.require(jobs == 2, 'Exactly two NF7 workers authorized')
    for state in (nf2, arithmetic):
        gate.require(state.get('LoadState') in ('loaded', 'not-found') and
            state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0',
            'Own NF2/arithmetic must be completed, including GC')
        if state['LoadState'] == 'not-found':
            gate.require(not state.get('ControlGroup'), 'Unknown active unit refused')
    external = []
    aliases = []
    for p in processes:
        normalized = {**p, 'argv': [a.split('=', 1)[1] if a.startswith('--') and '=' in a else a
                                    for a in p['argv']]}
        gate.require(not gate.owner(normalized, gate.NF2_UNIT, gate.NF2.parent) and
                     not gate.owner(normalized, gate.ARITH_UNIT, gate.ARITH), 'Own residual process refused')
        if Path(p['exe']).name == 'simv':
            (aliases if gate.owner(normalized, ALIAS_UNIT, ALIAS_OUT) else external).append(p)
    total = len(external) + max(len(aliases), 1) + 2
    gate.require(total <= 24, 'Live plus reserved simv exceeds authorized 24')
    gate.require(available >= 32*1024**3, 'Available memory below authorized 32 GiB')
    return dict(nf2=nf2, arithmetic=arithmetic, other_external_simvs=external, alias_simvs=aliases,
        other_external_count=len(external), alias_actual=len(aliases), alias_reserved=max(len(aliases), 1),
        nf7_jobs=2, total_live_reserved=total, available_bytes=available,
        ownership_snapshot=processes, external_processes_untouched=True)


def capacity_gate(plan, image, jobs):
    validate(plan)
    gate.old.verify(plan['nf2_terminal_pins'])
    gate.old.verify(plan['arithmetic_terminal_pins'])
    nf2 = gate.unit_state(gate.NF2_UNIT)
    arithmetic = gate.unit_state(gate.ARITH_UNIT)
    processes = snapshot.process_snapshot()
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0])*1024
    observation = dict(nf2=nf2, arithmetic=arithmetic, processes=processes,
        available_bytes=available, cpu_count=os.cpu_count(), PAM=snapshot.AUDIT, captured_unix=time.time())
    try:
        result = decide(nf2, arithmetic, processes, jobs, available)
    except Exception as error:
        gate.save(OUT / 'admission.json', dict(status='REFUSED_NO_NF7_LAUNCH', error=repr(error), **observation))
        raise
    result['terminal_pins'] = plan['arithmetic_terminal_pins']
    gate.save(OUT / 'admission.json', dict(status='PASS_TWO_NF7_RESERVED', gate=result,
        cpu_count=observation['cpu_count'], PAM=snapshot.AUDIT, captured_unix=observation['captured_unix']))
    return result


def preflight():
    gate.require(not OUT.exists(), 'Fresh output required')
    gate.require(gate.sha(SOURCE / 'plan.json') == SOURCE_SHA, 'Plan05 changed')
    plan = copy.deepcopy(gate.read(SOURCE / 'plan.json'))
    previous.validate(plan)
    gate.old.verify(plan['pins'])
    host = gate.read(HERE / 'resources06_host_tests.json')
    gate.require(host['status'] == 'HOST_RESOURCES06_PASS_NOT_DUT', 'Host checks missing')
    gate.old.verify(host['pins'])
    su = gate.accepted_helpers()
    image = su.check_image()
    su.parent_gate(image)
    gate.require(image['files'] == plan['image_files'], 'Image differs')
    OUT.mkdir()
    for n in ('programs', 'ledgers', 'groups'):
        (OUT / n).mkdir()
    names = ['programs/programs.json', 'reference_acceptance.json']
    names += [f'ledgers/g{g:02d}.json' for g in gate.old.GROUPS]
    for n in names:
        gate.save(OUT / n, gate.read(SOURCE / n))
        gate.require(gate.sha(OUT / n) == gate.sha(SOURCE / n), 'Accepted input changed')
    gate.save(OUT / 'admission_config.json', CONFIG)
    command = gate.old.command(OUT)
    command[command.index('--jobs')+1] = '2'
    gate.save(OUT / 'dryrun_command.json', command)
    with (OUT / 'dryrun.log').open('x') as log:
        subprocess.run(command, cwd=gate.old.ref.base.ROOT, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    rows = gate.read(OUT / 'dryrun/summary.json')
    gate.require(len(rows) == 24 and {x['name'] for x in rows} == {f'nf7_g{g:02d}' for g in gate.old.GROUPS}
                 and all(x['status'] == 'DRY_RUN' for x in rows), 'Dry-run differs')
    plan.update(predecessor_plan=str(SOURCE / 'plan.json'), predecessor_sha256=SOURCE_SHA,
        admission_config=CONFIG, delta='Parent scheduling authorization only: total24, memory32GiB, alias reserve1, NF7 two jobs')
    paths = [Path(__file__), HERE / 'test_resources06.py', HERE / 'resources06_host_tests.json',
        SOURCE / 'plan.json', OUT / 'admission_config.json', OUT / 'dryrun_command.json',
        OUT / 'dryrun/summary.json', *[OUT / n for n in names]]
    plan['pins'].update(gate.pins(paths))
    validate(plan)
    gate.old.verify(plan['pins'])
    gate.save(OUT / 'plan.json', plan)
    gate.save(OUT / 'preflight.json', dict(status='RESOURCES06_PREFLIGHT_PASS_NOT_LAUNCHED',
        plan_sha256=gate.sha(OUT / 'plan.json'), jobs=2, group_timeout_s=2400, group_outer_s=2700,
        service_outer_s=33600, VCS_started=False, one_actual_gate_deferred_to_worker=True))
    print('RESOURCES06_PREFLIGHT_PASS_NOT_LAUNCHED', gate.sha(OUT / 'plan.json'), flush=True)


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
        gate.OUT = OUT
        gate.capacity_gate = capacity_gate
        gate.old.validate_plan = validate
        try:
            gate.require(args.jobs == 2, 'Exactly two NF7 workers authorized')
            sys.exit(gate.worker(args.authorize_run, args.approved_plan_sha256, args.jobs))
        except Exception as error:
            if OUT.is_dir():
                gate.save(OUT / f'gate_refusal_{time.time_ns()}.json', dict(error=repr(error),
                    status='REFUSED_OR_ERROR_NOT_PASS', worker_record_exists=(OUT / 'worker.json').exists()))
            raise
