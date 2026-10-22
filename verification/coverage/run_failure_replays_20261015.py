#!/usr/bin/env python3
"""Exactly two evidence-justified timeout successors; no RTL/build/retry."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import signal
import sys
import threading

import replay_historical_extensions_20261015 as prior

ROOT = prior.ROOT
REVIEW = ROOT / 'verification/out/full-regression-failure-review-20261015-01/timeouts/proposed-replays'
BUDGETS = {'c0375': 600, 'e0784': 1200}


def prepare(name, output):
    source = REVIEW / name / 'proposed-command.json'
    reviewed = prior.read(source)
    old = reviewed['command']
    simv = Path(old[0]).resolve(strict=True)
    elf = Path(prior.plus(old, '+PRELOAD'))
    prior.require(reviewed['timeout_s'] == BUDGETS[name], 'unreviewed timeout')
    prior.require(prior.sha(simv) == reviewed['simv_sha256'] and
                  prior.sha(elf) == reviewed['elf_sha256'], 'image/ELF identity differs')
    case = output / name
    case.mkdir()
    work = case / 'work'
    work.mkdir()
    command = prior.rewrite(old, simv, work, elf)
    pins = {str(source): prior.sha(source), str(elf): reviewed['elf_sha256']}
    plan = dict(index=375 if name == 'c0375' else 784, name=name, directory=str(case),
                work=str(work), command=command, original_command=old, pins=pins,
                timeout_s=BUDGETS[name], elf_sha256=reviewed['elf_sha256'],
                vdb=str(work / 'code.vdb'),
                checker=dict(kind='ORIGINAL_SELF_CHECK_TRACE', contract_required=True,
                             scope='fresh firmware selfcheck, trace and unchanged CVXIF protocol checker'))
    prior.save(case / 'plan.json', plan)
    return plan


def check(plan):
    case = Path(plan['directory'])
    receipt = prior.read(case / 'simulation-exit.json')
    prior.require(receipt['executed'] is True and type(receipt['returncode']) is int and
                  receipt['returncode'] == 0 and not receipt['timed_out'] and not receipt['cancelled'],
                  'incomplete/nonzero actual simulator wait')
    result = prior.check_case(plan)
    if plan['name'] == 'c0375':
        text = (Path(plan['work']) / 'run.vcs.log').read_text()
        rows = re.findall(r'^QBS_REAL_BENCH (.*)$', text, re.M)
        prior.require(len(rows) == 1, 'one complete production benchmark record required')
        fields = dict(part.split('=', 1) for part in rows[0].split() if '=' in part)
        wanted = dict(case='q3k_decode_attn_q_qbs', result='PASS', k='1536', rows='256',
                      inputs='1', outputs='256', result_count='256')
        prior.require(all(fields.get(k) == v for k, v in wanted.items()), 'benchmark result/shape differs')
        prior.require('logical_read_bytes' in fields, 'truncated benchmark output')
        result['benchmark'] = fields
    else:
        collector = Path(__file__).with_name('audit_valu_replay_20261015.py')
        if not collector.is_file():
            return dict(status='CHECKER_REQUIRED', reason='full VALU audit not installed', generic=result)
        report = case / 'full-architecture'
        command = [sys.executable, str(collector), '--run', str(case), '--output', str(report)]
        waited = prior.child(command, ROOT, case / 'full-architecture.log', 600,
                             case / 'full-architecture-exit.json')
        prior.require(waited['returncode'] == 0 and not waited['timed_out'] and not waited['cancelled'],
                      'full VALU architecture audit did not pass')
        result['full_architecture'] = str(report)
    return result


def run_case(plan, update):
    case = Path(plan['directory'])
    row = dict(name=plan['name'], status='RUNNING', output=str(case))
    try:
        prior.verify(plan['pins'])
        actual = prior.child(plan['command'], Path(plan['work']), case / 'console.log',
                             plan['timeout_s'], case / 'simulation-exit.json',
                             lambda pid: update(dict(row, pid=pid)))
        row.update(actual_process_wait=actual)
        if actual['timed_out']:
            row.update(status='TIMEOUT')
        elif actual['cancelled']:
            row.update(status='CANCELLED')
        elif type(actual['returncode']) is not int or actual['returncode'] != 0:
            row.update(status='FAIL')
        else:
            update(dict(row, status='CHECKING'))
            result = check(plan)
            row.update(status=result['status'], audit=result, vdb=plan['vdb'])
        prior.verify(plan['pins'])
    except Exception as error:
        row.update(status='FAIL', reason=f'{type(error).__name__}: {error}')
    prior.save(case / 'result.json', row)
    update(row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    prior.require(not output.exists(), 'fresh output required; no overwrite or automatic retry')
    output.mkdir(parents=True)
    plans = [prepare(name, output) for name in BUDGETS]
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify.artifacts import simulation_image
    image = simulation_image(Path(plans[0]['command'][0]))
    prior.save(output / 'image-pins.json', image)
    prior.verify(image)
    state = dict(status='PREPARED', total=2, workers=2, cases={},
                 policy='same ELF/image; host wall budget only; no retry')
    lock = threading.Lock()

    def update(row):
        with lock:
            state['cases'][row['name']] = row
            state['counts'] = dict(prior.Counter(r['status'] for r in state['cases'].values()))
            prior.save(output / 'progress.json', state)

    prior.save(output / 'progress.json', state)
    if args.prepare_only:
        return 0
    state['status'] = 'RUNNING'
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: prior.STOP.set())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_case, plan, update) for plan in plans]
        for future in as_completed(futures):
            future.result()
    prior.verify(image)
    state['status'] = 'PASS' if all(r['status'] == 'PASS' for r in state['cases'].values()) else 'COMPLETE_WITH_NONPASS'
    state['image_unchanged'] = True
    prior.save(output / 'progress.json', state)
    print(json.dumps(dict(status=state['status'], counts=state['counts'])))
    return 0 if state['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
