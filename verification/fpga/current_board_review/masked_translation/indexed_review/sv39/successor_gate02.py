#!/usr/bin/env python3
"""GC-aware capacity successor. Preparation never launches simulation."""
import argparse
import copy
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import vcs_adapter as old
from support import HERE, read, save, accepted_helpers

require = old.require
sha = old.ref.base.sha
PREVIOUS = HERE / 'vcs_plan01'
PREVIOUS_SHA = 'fcad03c47c6bcb391c090b448289f8e6a6b65285177f6ab1e4fd9c2e8ed85d14'
OUT = HERE / 'vcs_plan02'
NF2 = HERE.parents[1] / 'segment_review/sv39/vcs_preflight01'
ARITH = old.ref.base.BASE / 'memory_regression_plan02'
NF2_UNIT = 'ara-nf2-candidate02.service'
ARITH_UNIT = 'ara-memory-arithmetic-plan02.service'
NF2_ELF = '2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67'


def pins(paths):
    return {str(p): sha(p) for p in paths}


def run_evidence(root, image, expected):
    run = read(root / 'run.json')
    summary = read(root / 'summary.json')
    require(run['status'] == 'COMPLETE' and bool(run.get('completed_at')),
            'Missing complete run evidence')
    require(run['simv'] == image['simv'] and run['tests'] == list(expected) and
            run['status_counts'] == {'PASS': len(expected)}, 'Run identity/status differs')
    require(len(summary) == len(expected) and {x['name'] for x in summary} == set(expected) and
            all(x['status'] == 'PASS' and x['returncode'] == 0 for x in summary),
            'Incomplete/non-PASS terminal summary')
    paths = [root / 'run.json', root / 'summary.json']
    for name, digest in expected.items():
        d = root / 'tests' / name
        inputs = read(d / 'inputs.json')
        require(inputs['binary']['sha256'] == digest and sha(d / 'input.elf') == digest,
                'Terminal input ELF drift')
        require(inputs['simv']['path'] == image['simv'] and
                inputs['simv']['image_sha256'] == image['files'], 'Terminal input image differs')
        require((d / 'commit_trace.csv').stat().st_size > 100, 'Missing commit CSV')
        paths += [d / n for n in ('inputs.json', 'input.elf', 'commit_trace.csv', 'console.log', 'command.json')]
    return pins(paths)


def nf2_evidence(image):
    complete = read(NF2 / 'complete.json')
    analysis = read(NF2 / 'csv_analysis.json')
    require(complete['status'] == 'CANDIDATE02_NF2_FOUR_PASS' and complete['returncode'] == 0,
            'NF2 terminal not PASS')
    require(complete['image_json_sha256'] == old.IMAGE_SHA and complete['soc_elf_sha256'] == NF2_ELF,
            'NF2 terminal identity changed')
    require(complete['analysis_sha256'] == sha(NF2 / 'csv_analysis.json') and
            analysis['status'] == 'NF2_CSV_ORACLE_PASS' and analysis['cases'] == list(range(4)) and
            analysis['checks'] == 4133 and len(analysis['checkpoints']) == 8,
            'NF2 full CSV oracle not PASS')
    require(complete['summary'] == read(NF2 / 'run/summary.json'), 'NF2 summary mismatch')
    preflight = read(NF2 / 'preflight.json')
    old.verify(preflight['pins'])
    result = run_evidence(NF2 / 'run', image, {'nf2_segment4': NF2_ELF})
    result.update(preflight['pins'])
    result.update(pins([NF2 / n for n in ('complete.json', 'csv_analysis.json', 'preflight.json', 'worker.json')]))
    return result


def arithmetic_identity(image):
    plan = read(ARITH / 'plan.json')
    launch = read(ARITH / 'launch.json')
    require(plan['image_sha256'] == old.IMAGE_SHA and plan['simv'] == image['simv'] and
            plan['jobs'] == 4 and plan['stop_first_fail'] and len(plan['cases']) == 38,
            'Arithmetic reviewed allocation/identity differs')
    require(launch['plan_sha256'] == sha(ARITH / 'plan.json') and launch['jobs'] == 4,
            'Arithmetic launch does not bind reviewed plan')
    return pins([ARITH / 'plan.json', ARITH / 'launch.json',
                 old.ref.base.BASE / 'replay_memory_regression.py',
                 old.ref.base.BASE / 'replay_memory_regression_successor.py'])


def arithmetic_evidence(image):
    complete = read(ARITH / 'complete.json')
    plan = read(ARITH / 'plan.json')
    require(complete['status'] == 'PASS_38_CANDIDATE02' and
            complete['plan_sha256'] == sha(ARITH / 'plan.json') and
            complete['image_sha256'] == old.IMAGE_SHA, 'Arithmetic terminal not matching full PASS')
    expected = {x['id']: x['sha256'] for x in plan['cases']}
    require(len(expected) == 38 and len(complete['results']) == 38 and
            {x['name'] for x in complete['results']} == set(expected) and
            all(x['status'] == 'PASS' for x in complete['results']), 'Arithmetic partial/failed completion')
    old.verify(plan['pins'])
    result = run_evidence(ARITH / 'replay', image, expected)
    result.update(plan['pins'])
    result.update(arithmetic_identity(image))
    result.update(pins([ARITH / 'complete.json']))
    return result


def unit_state(unit):
    require(unit in (NF2_UNIT, ARITH_UNIT), 'Unknown capacity unit name')
    output = subprocess.check_output(['systemctl', '--user', 'show', unit,
        '-p', 'LoadState', '-p', 'ActiveState', '-p', 'MainPID', '-p', 'Result', '-p', 'ControlGroup'],
        text=True, timeout=10)
    state = dict(line.split('=', 1) for line in output.splitlines())
    require(state.get('LoadState') in ('loaded', 'not-found'), 'Unrecognized unit load state')
    if state['LoadState'] == 'not-found':
        require(state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0' and
                not state.get('ControlGroup'), 'Unknown active unit refused')
    return state


def process_snapshot():
    """One snapshot, no wait loop; inspect non-simv owners as well as every simv."""
    result = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            comm = (p / 'comm').read_text().strip()
            if p.stat().st_uid != os.getuid() and comm != 'simv':
                continue
            stat = (p / 'stat').read_text().rsplit(')', 1)[1].split()
            if stat[0] == 'Z':
                continue
            cgroups = [x.split(':', 2)[2] for x in (p / 'cgroup').read_text().splitlines()]
            result.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve(strict=True)),
                argv=(p / 'cmdline').read_bytes().decode(errors='replace').split('\0'),
                cwd=str((p / 'cwd').resolve(strict=True)), cgroups=cgroups, starttime=stat[19]))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            raise ValueError('Cannot inspect capacity process: ' + p.name) from error
    return result


def member(process, group):
    return bool(group) and any(x == group or x.startswith(group + '/') for x in process['cgroups'])


def owner(process, unit, root):
    return (any(unit in x.split('/') for x in process['cgroups']) or
            process['cwd'] == str(root) or process['cwd'].startswith(str(root) + '/') or
            any(x == str(root) or x.startswith(str(root) + '/') for x in process['argv']))


def decide(nf2, arithmetic, processes, jobs, nf2_pass, arithmetic_pass, image):
    require(1 <= jobs <= 4, 'NF7 allocation exceeds four')
    for state in (nf2, arithmetic):
        require(state.get('LoadState') in ('loaded', 'not-found'), 'Unknown unit state')
        if state['LoadState'] == 'not-found':
            require(state.get('ActiveState') == 'inactive' and state.get('MainPID') == '0' and
                    not state.get('ControlGroup'), 'Unknown active unit refused')
    require(nf2['ActiveState'] == 'inactive' and nf2['MainPID'] == '0' and nf2_pass,
            'NF2 must have pinned full PASS and be terminal')
    require(not any(owner(p, NF2_UNIT, NF2.parent) for p in processes), 'NF2 owned process remains')
    simvs = [p for p in processes if Path(p['exe']).name == 'simv']
    live = arithmetic['LoadState'] == 'loaded' and arithmetic['ActiveState'] == 'active'
    if live:
        require(arithmetic['MainPID'] != '0' and bool(arithmetic.get('ControlGroup')),
                'Arithmetic active unit lacks main owner')
        require(any(p['pid'] == int(arithmetic['MainPID']) and member(p, arithmetic['ControlGroup']) and
                    str(ARITH) in p['argv'] for p in processes), 'Arithmetic main process identity differs')
        for p in simvs:
            require(member(p, arithmetic['ControlGroup']) and p['exe'] == image['simv'] and
                    p['cwd'].startswith(str(ARITH / 'replay/tests') + '/'), 'Alien simv refused')
    else:
        require(arithmetic['ActiveState'] == 'inactive' and arithmetic['MainPID'] == '0' and arithmetic_pass,
                'Arithmetic terminal requires pinned complete PASS')
        require(not simvs and not any(owner(p, ARITH_UNIT, ARITH) for p in processes),
                'Terminal arithmetic still owns processes or another simv exists')
    require(len(simvs) <= 4 and len(simvs) + jobs <= 8, 'Actual/reserved simulation capacity exceeded')
    return dict(nf2=nf2, arithmetic=arithmetic, arithmetic_pids=[p['pid'] for p in simvs],
                nf7_jobs=jobs, total_reserved_max_jobs=jobs + (4 if live else 0),
                ownership_snapshot=processes, no_polling=True)


def capacity_gate(plan, image, jobs):
    nf2 = unit_state(NF2_UNIT)
    arithmetic = unit_state(ARITH_UNIT)
    old.verify(plan['nf2_terminal_pins'])
    terminal_pins = {}
    if arithmetic['ActiveState'] != 'active':
        terminal_pins = arithmetic_evidence(image)
        old.verify(terminal_pins)
    # Scan after potentially expensive evidence hashing, immediately before admission.
    result = decide(nf2, arithmetic, process_snapshot(), jobs, True, bool(terminal_pins), image)
    result['terminal_pins'] = terminal_pins
    return result


def preflight():
    require(not OUT.exists(), 'Fresh plan02 required')
    require(sha(PREVIOUS / 'plan.json') == PREVIOUS_SHA, 'Sealed plan01 changed')
    previous = read(PREVIOUS / 'plan.json')
    old.validate_plan(previous)
    old.verify(previous['pins'])
    su = accepted_helpers()
    image = su.check_image()
    su.parent_gate(image)
    require(image['files'] == previous['image_files'], 'Image differs from plan01')
    nf2 = nf2_evidence(image)
    arithmetic = arithmetic_identity(image)
    host = read(HERE / 'gate02_host_tests.json')
    require(host['status'] == 'HOST_GC_GATE_PASS_NOT_DUT', 'GC host negatives missing')
    old.verify(host['pins'])
    OUT.mkdir()
    for name in ('programs', 'ledgers', 'groups'):
        (OUT / name).mkdir()
    for name in ('programs/programs.json', 'reference_acceptance.json'):
        save(OUT / name, read(PREVIOUS / name))
        require(sha(OUT / name) == sha(PREVIOUS / name), 'Copied accepted record changed')
    for g in old.GROUPS:
        name = f'ledgers/g{g:02d}.json'
        save(OUT / name, read(PREVIOUS / name))
        require(sha(OUT / name) == sha(PREVIOUS / name), 'Accepted comparison ledger changed')
    command = old.command(OUT)
    save(OUT / 'dryrun_command.json', command)
    with (OUT / 'dryrun.log').open('x') as log:
        subprocess.run(command, cwd=old.ref.base.ROOT, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    summary = read(OUT / 'dryrun/summary.json')
    require(len(summary) == 24 and {x['name'] for x in summary} == {f'nf7_g{g:02d}' for g in old.GROUPS}
            and all(x['status'] == 'DRY_RUN' for x in summary), 'Dry-run scope differs')
    plan = copy.deepcopy(previous)
    plan.update(predecessor_plan=str(PREVIOUS / 'plan.json'), predecessor_sha256=PREVIOUS_SHA,
        nf2_terminal_pins=nf2, capacity_units=[NF2_UNIT, ARITH_UNIT],
        delta='GC-aware evidence/ownership capacity gate and persistent service log only',
        arithmetic_terminal_policy='If terminal at launch: require complete38 PASS, pin raw CSV/run/ELF/image evidence before admission and reverify post-run')
    paths = [Path(__file__), HERE / 'test_gate02.py', HERE / 'gate02_host_tests.json',
        PREVIOUS / 'plan.json', OUT / 'programs/programs.json', OUT / 'reference_acceptance.json',
        OUT / 'dryrun_command.json', OUT / 'dryrun/summary.json', *sorted((OUT / 'ledgers').glob('*.json'))]
    plan['pins'].update(nf2)
    plan['pins'].update(arithmetic)
    plan['pins'].update(pins(paths))
    old.validate_plan(plan)
    old.verify(plan['pins'])
    require(su.check_image() == image, 'Preflight image drift')
    save(OUT / 'plan.json', plan)
    save(OUT / 'preflight.json', dict(status='GC02_READY_NOT_LAUNCHED', VCS_started=False,
        plan_sha256=sha(OUT / 'plan.json'), predecessor_sha256=PREVIOUS_SHA,
        same24_elf_and_ledgers=True, group_timeout_s=2400, group_outer_s=2700, max_jobs=4,
        service_outer_s=16800, capacity_deferred_until_explicit_worker=True))
    print('GC02_READY_NOT_LAUNCHED', sha(OUT / 'plan.json'), flush=True)


def worker(authorized, approved_sha, jobs):
    require(authorized, 'Preparation is not run authorization')
    require(approved_sha == sha(OUT / 'plan.json'), 'Parent-approved plan02 hash required')
    plan = read(OUT / 'plan.json')
    old.validate_plan(plan)
    old.verify(plan['pins'])
    su = accepted_helpers()
    image = su.check_image()
    require(image['files'] == plan['image_files'] and sha(old.IMAGE / 'image.json') == old.IMAGE_SHA,
            'Different candidate image')
    su.parent_gate(image)
    gate = capacity_gate(plan, image, jobs)
    save(OUT / 'worker.json', dict(pid=os.getpid(), start_unix=time.time(), gate=gate,
        jobs=jobs, plan_sha256=approved_sha))
    abort = old.scheduler.Abort()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: abort.stop(dict(signal=signum)))
    results = old.scheduler.run_groups(old.GROUPS, jobs, lambda g, a: old.group_worker(OUT, g, a), abort)
    passed = all(results[g]['status'] == 'PASS' for g in old.GROUPS)
    post = 'UNCHANGED'
    try:
        old.verify(plan['pins'])
        old.verify(gate['terminal_pins'])
        require(su.check_image() == image, 'Post-run image drift')
        require(sha(OUT / 'plan.json') == approved_sha, 'Plan changed during run')
    except Exception as error:
        passed = False
        post = str(error)
    save(OUT / 'complete.json', dict(status='NF7_FULL96_PASS' if passed else 'NF7_FULL96_NOT_PASS',
        groups=results, firstfailure=abort.reason, post_hashes=post, scope=plan['scope'],
        image_sha256=old.IMAGE_SHA, plan_sha256=approved_sha))
    return int(not passed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'worker'))
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    try:
        if args.action == 'preflight':
            preflight()
        else:
            sys.exit(worker(args.authorize_run, args.approved_plan_sha256, args.jobs))
    except Exception as error:
        if args.action == 'worker' and OUT.is_dir():
            save(OUT / f'gate_refusal_{time.time_ns()}.json', dict(status='REFUSED_OR_ERROR_NOT_PASS',
                error=repr(error), worker_record_exists=(OUT / 'worker.json').exists()))
        raise
