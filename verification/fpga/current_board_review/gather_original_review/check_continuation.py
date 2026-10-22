#!/usr/bin/env python3
"""Require a raw-validated inherited control and seven new raw-validated results."""
import argparse
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
from prepare_batch import HERE, sha, save
from check_terminal import read, require
import check_successor as stage_checker

CONTROL = HERE / 'successor01/vcs_candidate04_01'
CONTROL_HASH = 'a132b635e168317e013cccbf1e6a4b938b54330923ae5f3abd98d86b85f7314b'
NAMES = stage_checker.NAMES


def inherited_control(origin=CONTROL, plan_hash=CONTROL_HASH):
    require(origin.resolve() == CONTROL.resolve() and plan_hash == CONTROL_HASH,
            'Wrong inherited control anchor')
    gate = read(origin / 'control/independent_gate.json')
    require(gate['status'] == 'PASS_CONTROL' and gate['plan_sha256'] == plan_hash,
            'Inherited independent control not PASS')
    # Raw oracle, exit, ELF, trace, image and original pins are revalidated;
    # presence or timing of a startup-monitor file is not a terminal oracle.
    results = stage_checker.validate_stage(origin, plan_hash, 'control')
    require(results == gate['results'] and len(results) == 1 and results[0]['name'] == NAMES[0],
            'Inherited result drift')
    return dict(status='PASS_TERMINAL_CONTROL', source=str(origin), plan_sha256=plan_hash,
                results=results, rerun_control=False, raw_artifacts_revalidated=True)


def verify_progress(out, plan, confirmation, worker):
    require(confirmation['status'] == 'ADVANCING_2_SIMV' and
            confirmation['raw_samples_retained'] is True and
            len(confirmation['samples']) == 2, 'Two real remaining workers not confirmed')
    before, after = confirmation['samples']
    require(len(before) == len(after) == 2 and len({x['pid'] for x in before}) == 2,
            'Wrong real PID count')
    simv = read(Path(plan['image']) / 'image.json')['simv']
    require(confirmation['worker_cgroup'] == worker['cgroup'], 'Worker cgroup anchor differs')
    for a,b in zip(before,after):
        require(a['pid'] == b['pid'] and b['cpu_ticks'] > a['cpu_ticks'] and
                b['trace_bytes'] > a['trace_bytes'] > 0 and
                b['last_cycle'] > a['last_cycle'] > 0, 'Raw PID/CPU/trace/cycle growth failed')
        require(a['executable'] == b['executable'] == str(Path(simv).resolve()) and
                a['cgroup'] == b['cgroup'] == worker['cgroup'] and
                a['argv'] == b['argv'] and a['cwd'] == b['cwd'], 'Raw process identity differs')
        argv = b['argv']
        names = [x.split('=', 1)[1] for x in argv if x.startswith('+TESTCASE=')]
        require(len(names) == 1 and names[0] in NAMES[1:] and argv[0] == simv, 'Wrong real case/image')
        case = out / 'remaining7/replay/tests' / names[0]
        require(b['cwd'] == str(case / 'work'), 'Wrong real work directory')
        for prefix,value in (('+PRELOAD=', str(case / 'input.elf')),
                             ('+COMMIT_TRACE=', str(case / 'commit_trace.csv'))):
            require([x for x in argv if x.startswith(prefix)] == [prefix+value], 'Wrong real private input/trace')


def validate(out, plan_hash):
    require(sha(out / 'plan.json') == plan_hash, 'Continuation plan drift')
    plan = read(out / 'plan.json')
    require(plan['control_source'] == str(CONTROL) and plan['control_plan_sha256'] == CONTROL_HASH and
            plan['run_names'] == NAMES[1:] and plan['skip_control_execution'] is True,
            'Continuation would rerun/change control')
    inherited = inherited_control()
    stage_checker.check_pins(plan)
    worker = read(out / 'worker_exit.json')
    require(worker['plan_sha256'] == plan_hash and worker['runner_returncode'] == 0 and
            worker['error'] is None, 'Continuation worker not exit0')
    confirmation = read(out / 'remaining7/actual_simv_confirmation.json')
    verify_progress(out, plan, confirmation, read(out / 'worker.json'))
    results = stage_checker.validate_stage(out, plan_hash, 'remaining7')
    stage_checker.check_pins(plan)
    return inherited, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    try:
        inherited, results = validate(out, args.plan_sha256)
        final = dict(status='PASS_1_INHERITED_CONTROL_PLUS_7_CANDIDATE04',
            inherited_control=inherited, results=results, pins_unchanged=True,
            control_rerun=False, retries=0, finished=time.time(), plan_sha256=args.plan_sha256,
            scope='Eight exact source tuples across two records; not Linux ELF/parent matrices/83/board acceptance')
        rc = 0
    except Exception as error:
        final = dict(status='NOT_ACCEPTED', reason=str(error), retries=0,
                     finished=time.time(), plan_sha256=args.plan_sha256)
        for name in ('worker_exit.json', 'remaining7/replay/summary.json',
                     'remaining7/actual_simv_confirmation.json'):
            if (out / name).exists():
                final[name] = read(out / name)
        rc = 1
    save(out / 'complete.json', final)
    print(final['status'], final.get('reason', ''), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
