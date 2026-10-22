#!/usr/bin/env python3
"""Independent raw-output, exit, membership, staged ELF, trace and pin acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
EXPECTED = ['gather_e16_m1_ops0', 'gather_e8_mf8', 'gather_e16_mf4',
            'gather_e16_m1_ops1', 'gather_e32_m1_ops2', 'gather_e64_m1_ops3',
            'gather_e32_m8_ops20', 'gather_e64_m8_ops0']
VETO = re.compile(r'RVV_PERMUTE_(?:FAIL|CAPACITY_FAIL|DETAIL)\b|BOARD_CASE_FAIL\b|'
                  r'BOARD_REPLAY_[A-Z_]*(?:FAIL|TRAP|MISMATCH)\b|\bSKIP\b|'
                  r'Core Test \*\*\* FAILED \*\*\*|\bUVM_FATAL\b(?!\s*:\s*0\b)|'
                  r'\$fatal\b|\bFatal\s*:|(?:Error|Fatal)[^\n]*(?:assertion|assert)[^\n]*fail|'
                  r'^\s*(?:Index\s+\d+\s+)?(?:FAIL(?:ED|URE)?|FATAL)\b', re.I | re.M)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def console_check(text, name):
    require(not VETO.search(text), name + ': failure-marker veto')
    sew = re.search(r'_e(8|16|32|64)_', name)[1]
    lines = text.splitlines()
    for prefix, expected in (
        ('RVV_PERMUTE_PASS', f'RVV_PERMUTE_PASS sew={sew} cases=1 errors=0'),
        ('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + name),
        ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + name),
        ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS'),
        ('Core Test *** SUCCESS ***', 'Core Test *** SUCCESS *** (tohost = 0)'),
    ):
        require([line for line in lines if line.startswith(prefix)] == [expected], name + ': missing/ambiguous ' + prefix)


def validate(out, plan_hash):
    require(sha(out / 'plan.json') == plan_hash, 'Plan hash drift')
    plan = read(out / 'plan.json')
    require(plan['names'] == EXPECTED and plan['jobs'] == 2 and plan['timeout_per_case_s'] == 300 and plan['retries'] == 0, 'Wrong authorized plan')
    for path, digest in plan['pins'].items():
        require(sha(path) == digest, 'Pinned input drift: ' + path)
    worker = read(out / 'worker_exit.json')
    require(worker['plan_sha256'] == plan_hash and worker['runner_returncode'] == 0 and worker['error'] is None, 'Runner did not exit0')
    run = read(out / 'replay/run.json')
    summary = read(out / 'replay/summary.json')
    image = read(Path(plan['image']) / 'image.json')
    programs = read(Path(plan['programs']) / 'programs.json')['programs']
    require(list(programs) == EXPECTED, 'Program membership drift')
    require(run['status'] == 'COMPLETE' and run.get('completed_at') and
            run['tests'] == EXPECTED and run['jobs'] == 2 and
            run['status_counts'] == {'PASS': 8} and run['simv'] == image['simv'], 'Run not exact COMPLETE/PASS8')
    require(len(summary) == 8 and [r['name'] for r in summary] == EXPECTED, 'Summary membership/count differs')
    sys.path.insert(0, str(Path(image['snapshot']) / 'sources/verification'))
    from ara_verify.trace import validate_trace
    results = []
    for result in summary:
        name = result['name']
        folder = out / 'replay/tests' / name
        require(result['status'] == 'PASS' and result['returncode'] == 0 and not result['reason'] and result['artifact_dir'] == str(folder), name + ': notPASS/exit0')
        entry = programs[name]
        inputs = read(folder / 'inputs.json')
        private = folder / 'input.elf'
        require(sha(private) == entry['sha256'] and inputs['binary'] ==
                dict(source=entry['path'], path=str(private), sha256=entry['sha256']), name + ': staged ELF drift')
        require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), name + ': staged image drift')
        command = read(folder / 'command.json')
        argv = command['command']
        require(command['cwd'] == str(folder / 'work') and argv[0] == image['simv'], name + ': wrong image/cwd')
        for prefix, value in (('+PRELOAD=', str(private)), ('+TESTCASE=', name),
                              ('+COMMIT_TRACE=', str(folder / 'commit_trace.csv'))):
            require([a for a in argv if a.startswith(prefix)] == [prefix + value], name + ': wrong command identity')
        require('+NO_FSDB' in argv and not any(a in ('-cm', '-ucli') for a in argv), name + ': unexpected instrumentation')
        for log in (folder / 'console.log', folder / 'work/run.vcs.log'):
            console_check(log.read_text(), name)
        trace = validate_trace(folder / 'commit_trace.csv')
        require(trace.get('rows', 0) > 0 and trace.get('last_cycle', 0) > 0, name + ': empty trace')
        require(trace['cvx_exception_count'] == 0, name + ': unexpected vector trap')
        results.append(dict(name=name, status='PASS', returncode=0, elapsed_s=result['elapsed_s'],
                            elf_sha256=sha(private), console_sha256=sha(folder / 'console.log'),
                            trace_sha256=sha(folder / 'commit_trace.csv'), trace=trace))
    for path, digest in plan['pins'].items():
        require(sha(path) == digest, 'Postcheck input drift: ' + path)
    return results, len(plan['pins'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    try:
        results, count = validate(out, args.plan_sha256)
        final = dict(status='PASS_8_ORIGINAL_SINGLES_CANDIDATE03', results=results,
                     pins_verified=count, pins_unchanged=True, failure_marker_veto=True,
                     plan_sha256=args.plan_sha256, finished=time.time(), retries=0,
                     scope='Eight source singles, not83/full parent matrices/Linux board closure')
        code = 0
    except Exception as error:
        final = dict(status='NOT_ACCEPTED', reason=str(error), plan_sha256=args.plan_sha256,
                     finished=time.time(), retries=0)
        for file in ('worker_exit.json', 'replay/run.json', 'replay/summary.json'):
            if (out / file).is_file():
                final[file] = read(out / file)
        code = 1
    (out / 'complete.json').write_text(json.dumps(final, indent=2) + '\n')
    print(final['status'], final.get('reason', ''), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
