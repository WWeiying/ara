#!/usr/bin/env python3
"""Snapshot-only successor: classify readable metadata before exe/cwd access."""
import argparse
import copy
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import successor_gate02 as gate

HERE = gate.HERE
PREVIOUS = HERE / 'vcs_plan02'
PREVIOUS_SHA = '86b5757f4be671cd4cb5227491b9a181b785566075cfc2d097543bf52e13edd4'
OUT = HERE / 'vcs_plan03'
AUDIT = []


def relevant(comm, cgroups, argv):
    if comm == 'simv' or any(Path(a).name == 'simv' for a in argv if a):
        return True
    if any(u in group.split('/') for group in cgroups for u in (gate.NF2_UNIT, gate.ARITH_UNIT)):
        return True
    roots = (str(gate.NF2.parent), str(gate.ARITH))
    return any(a == r or a.startswith(r + '/') or a.startswith('--') and
               '=' in a and (a.split('=', 1)[1] == r or a.split('=', 1)[1].startswith(r + '/'))
               for a in argv for r in roots)


def inspect_process(p):
    try:
        comm = (p / 'comm').read_text().strip()
        uid = p.stat().st_uid
        if uid != os.getuid() and comm != 'simv':
            return None
        stat = (p / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        cgroups = [x.split(':', 2)[2] for x in (p / 'cgroup').read_text().splitlines()]
        argv = (p / 'cmdline').read_bytes().decode(errors='replace').split('\0')
        if not relevant(comm, cgroups, argv):
            if comm == '(sd-pam)':
                AUDIT.append(dict(pid=int(p.name), uid=uid, comm=comm, cgroups=cgroups,
                    argv=argv, decision='IRRELEVANT_METADATA_NO_EXE_OR_CWD_ACCESS'))
            return None
        return dict(pid=int(p.name), exe=str((p / 'exe').resolve(strict=True)),
            argv=argv, cwd=str((p / 'cwd').resolve(strict=True)), cgroups=cgroups, starttime=stat[19])
    except (FileNotFoundError, ProcessLookupError):
        return None
    except PermissionError as error:
        raise ValueError('Cannot inspect potentially relevant capacity process: ' + p.name) from error


def process_snapshot():
    AUDIT.clear()
    result = []
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            record = inspect_process(p)
            if record is not None:
                result.append(record)
    return result


def configure():
    gate.OUT = OUT
    gate.process_snapshot = process_snapshot


def preflight():
    gate.require(not OUT.exists(), 'Fresh snapshot03 output required')
    gate.require(gate.sha(PREVIOUS / 'plan.json') == PREVIOUS_SHA, 'Sealed plan02 changed')
    plan = copy.deepcopy(gate.read(PREVIOUS / 'plan.json'))
    gate.old.validate_plan(plan)
    gate.old.verify(plan['pins'])
    host = gate.read(HERE / 'snapshot03_host_tests.json')
    gate.require(host['status'] == 'HOST_SNAPSHOT03_PASS_NOT_DUT', 'Host snapshot tests missing')
    gate.old.verify(host['pins'])
    su = gate.accepted_helpers()
    image = su.check_image()
    su.parent_gate(image)
    gate.require(image['files'] == plan['image_files'] and
                 gate.sha(gate.old.IMAGE / 'image.json') == gate.old.IMAGE_SHA, 'Image drift')
    OUT.mkdir()
    for name in ('programs', 'ledgers', 'groups'):
        (OUT / name).mkdir()
    names = ['programs/programs.json', 'reference_acceptance.json']
    names += [f'ledgers/g{g:02d}.json' for g in gate.old.GROUPS]
    for name in names:
        gate.save(OUT / name, gate.read(PREVIOUS / name))
        gate.require(gate.sha(OUT / name) == gate.sha(PREVIOUS / name), 'Accepted input changed')
    command = gate.old.command(OUT)
    gate.save(OUT / 'dryrun_command.json', command)
    with (OUT / 'dryrun.log').open('x') as log:
        subprocess.run(command, cwd=gate.old.ref.base.ROOT, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    summary = gate.read(OUT / 'dryrun/summary.json')
    gate.require(len(summary) == 24 and {x['name'] for x in summary} ==
        {f'nf7_g{g:02d}' for g in gate.old.GROUPS} and all(x['status'] == 'DRY_RUN' for x in summary),
        'Dry-run scope differs')
    configure()
    print('Beginning one read-only REAL capacity_gate; no worker or simulation launch', flush=True)
    try:
        result = gate.capacity_gate(plan, image, 4)
    except Exception as error:
        gate.save(OUT / 'real_capacity_gate.json', dict(status='REAL_GATE_REFUSED_NOT_LAUNCHED',
            error=repr(error), snapshot_audit=AUDIT, VCS_started=False))
        raise
    gate.save(OUT / 'real_capacity_gate.json', dict(status='REAL_CAPACITY_GATE_PASS_NOT_LAUNCHED',
        captured_unix=time.time(), gate=result, snapshot_audit=AUDIT, VCS_started=False))
    plan.update(predecessor_plan=str(PREVIOUS / 'plan.json'), predecessor_sha256=PREVIOUS_SHA,
        delta='Only process snapshot metadata classification before exe/cwd; original evidence/capacity policy unchanged')
    plan['pins'].update(result['terminal_pins'])
    plan['pins'].update(gate.pins([Path(__file__), HERE / 'test_snapshot03.py',
        HERE / 'snapshot03_host_tests.json', PREVIOUS / 'plan.json', OUT / 'real_capacity_gate.json',
        OUT / 'dryrun_command.json', OUT / 'dryrun/summary.json', *[OUT / n for n in names]]))
    gate.old.verify(plan['pins'])
    gate.require(su.check_image() == image, 'Post-preflight image drift')
    gate.save(OUT / 'plan.json', plan)
    gate.save(OUT / 'preflight.json', dict(status='SNAPSHOT03_READY_NOT_LAUNCHED',
        plan_sha256=gate.sha(OUT / 'plan.json'), same24_elf_and_ledgers=True,
        real_capacity_gate='PASS_ONCE_NOT_A_FUTURE_CAPACITY_RESERVATION', VCS_started=False,
        group_timeout_s=2400, group_outer_s=2700, max_jobs=4, service_outer_s=16800))
    print('SNAPSHOT03_READY_NOT_LAUNCHED', gate.sha(OUT / 'plan.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'worker'))
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if args.action == 'preflight':
        preflight()
    else:
        configure()
        try:
            sys.exit(gate.worker(args.authorize_run, args.approved_plan_sha256, args.jobs))
        except Exception as error:
            if OUT.is_dir():
                gate.save(OUT / f'gate_refusal_{time.time_ns()}.json', dict(error=repr(error),
                    status='REFUSED_OR_ERROR_NOT_PASS', snapshot_audit=AUDIT,
                    worker_record_exists=(OUT / 'worker.json').exists()))
            raise
