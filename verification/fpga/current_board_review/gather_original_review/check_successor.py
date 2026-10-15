#!/usr/bin/env python3
"""Independent raw-artifact acceptance for the two successor stages."""
import argparse
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
from prepare_batch import HERE, SELECTED, sha, save
from check_terminal import console_check, read, require

NAMES = ['gather_' + s for s in SELECTED]


def check_pins(plan):
    for path, digest in plan['pins'].items():
        require(sha(Path(path)) == digest, 'Pinned input drift: ' + path)


def validate_stage(out, plan_hash, stage):
    require(sha(out / 'plan.json') == plan_hash, 'Plan drift')
    plan = read(out / 'plan.json')
    require(plan['names'] == NAMES and plan['jobs'] == 2 and
            plan['timeout_per_case_s'] == 300 and plan['retries'] == 0,
            'Wrong authorized plan')
    require(plan['stages'] == [dict(name='control', cases=NAMES[:1], jobs=1),
                              dict(name='remaining7', cases=NAMES[1:], jobs=2)], 'Wrong order')
    check_pins(plan)
    expected = next(s for s in plan['stages'] if s['name'] == stage)
    folder = out / stage / 'replay'
    summary = read(folder / 'summary.json')
    run = read(folder / 'run.json')
    image = read(Path(plan['image']) / 'image.json')
    programs = read(Path(plan['programs']) / 'programs.json')['programs']
    require(list(programs) == NAMES, 'Wrong8 program membership')
    require(run['status'] == 'COMPLETE' and run.get('completed_at') and
            run['tests'] == expected['cases'] and run['jobs'] == expected['jobs'] and
            run['simv'] == image['simv'] and
            run['status_counts'] == {'PASS': len(expected['cases'])}, 'Stage not all COMPLETE/PASS')
    require(len(summary) == len(expected['cases']) and
            [r['name'] for r in summary] == expected['cases'], 'Summary membership differs')
    sys.path.insert(0, str(Path(image['snapshot']) / 'sources/verification'))
    from ara_verify.trace import validate_trace
    results = []
    for result in summary:
        name = result['name']
        case = folder / 'tests' / name
        require(result['status'] == 'PASS' and result['returncode'] == 0 and
                not result['reason'] and result['artifact_dir'] == str(case), name + ': not PASS/exit0')
        entry = programs[name]
        inputs = read(case / 'inputs.json')
        private = case / 'input.elf'
        require(sha(private) == entry['sha256'] and inputs['binary'] ==
                dict(source=entry['path'], path=str(private), sha256=entry['sha256']), name + ': ELF drift')
        require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), name + ': image drift')
        command = read(case / 'command.json')
        argv = command['command']
        require(command['cwd'] == str(case / 'work') and argv[0] == image['simv'], name + ': wrong image/cwd')
        for prefix, value in (('+PRELOAD=', str(private)), ('+TESTCASE=', name),
                              ('+COMMIT_TRACE=', str(case / 'commit_trace.csv'))):
            require([a for a in argv if a.startswith(prefix)] == [prefix+value], name + ': command identity')
        require('+NO_FSDB' in argv and not any(a in ('-cm', '-ucli') for a in argv), 'Unexpected instrumentation')
        for log in (case / 'console.log', case / 'work/run.vcs.log'):
            console_check(log.read_text(), name)
        trace = validate_trace(case / 'commit_trace.csv')
        require(trace.get('rows', 0) > 0 and trace.get('last_cycle', 0) > 0 and
                trace['cvx_exception_count'] == 0, name + ': invalid/empty/trapping trace')
        results.append(dict(name=name, status='PASS', returncode=0, elapsed_s=result['elapsed_s'],
            elf_sha256=sha(private), console_sha256=sha(case / 'console.log'),
            trace_sha256=sha(case / 'commit_trace.csv'), trace=trace))
    check_pins(plan)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--stage', choices=('control', 'remaining7'))
    args = parser.parse_args()
    out = args.out.resolve()
    destination = out / args.stage / 'independent_gate.json' if args.stage else out / 'complete.json'
    try:
        if args.stage:
            results = validate_stage(out, args.plan_sha256, args.stage)
            status = 'PASS_' + args.stage.upper()
        else:
            worker = read(out / 'worker_exit.json')
            require(worker['plan_sha256'] == args.plan_sha256 and
                    worker['runner_returncode'] == 0 and worker['error'] is None, 'Worker not exit0')
            results = []
            for stage in ('control', 'remaining7'):
                require(read(out / stage / 'independent_gate.json')['status'] == 'PASS_'+stage.upper(),
                        'Missing prior independent stage acceptance')
                results.extend(validate_stage(out, args.plan_sha256, stage))
            status = 'PASS_8_TUPLE_SUCCESSORS_CANDIDATE04'
        final = dict(status=status, results=results, pins_unchanged=True,
            plan_sha256=args.plan_sha256, finished=time.time(), retries=0,
            scope='Eight narrowed exact source tuples; not original Linux ELF/parent matrices/83/board acceptance')
        code = 0
    except Exception as error:
        final = dict(status='NOT_ACCEPTED', reason=str(error), plan_sha256=args.plan_sha256,
                     finished=time.time(), retries=0)
        for stage in ('control', 'remaining7'):
            file = out / stage / 'replay/summary.json'
            if file.exists():
                final[stage+'_summary'] = read(file)
        code = 1
    save(destination, final)
    print(final['status'], final.get('reason', ''), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
