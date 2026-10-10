#!/usr/bin/env python3
"""Timing-only successor for the sealed one-load native singleton batch."""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import lzc_selector_native_product_batch as batch
from lzc_selector_native_prepare import require, sha, write

HERE = Path(__file__).resolve().parent
DVE_SECONDS = 10500
WATCHDOG_SECONDS = 10530
MAX_WORKFLOW_SECONDS = 10800


def estimate(plan, discovery_seconds):
    rows = plan['protection_rows']
    scopes = Counter(r['scope'] for r in rows)
    require(len(rows) == 4200 and len(plan['targets']) == 120 and discovery_seconds > 0,
            'Exact reviewed workload and positive discovery timing required')
    native_parents = {}
    for row in rows:
        if row['metric'] == 'branch':
            native_parents.setdefault(row['scope'], set()).add(row['native_id'])
    local = sum(5 * scopes[t['candidate']['scope']] for t in plan['targets'])
    global_checks = 2 * len(rows)
    cells = sum(6 * len(native_parents[t['candidate']['scope']]) for t in plan['targets']
                if t['candidate']['metric'] == 'branch')
    targets = len(plan['targets'])
    operations = dict(save=5 * targets + 2, load=targets, recalculate=2 * targets, reset=2 * targets + 1)
    proxy = discovery_seconds / len(rows)
    model = discovery_seconds + (local + global_checks + cells) * proxy + sum(operations.values())
    with_margin = math.ceil(model * 1.25)
    require(with_margin <= DVE_SECONDS and WATCHDOG_SECONDS < MAX_WORKFLOW_SECONDS,
            'Measured workload planning model exceeds bounded successor; no silent timeout clipping')
    return dict(discovery_observed_seconds=discovery_seconds, discovery_positions=len(rows),
        local_five_stage_state_checks=local, global_before_final_state_checks=global_checks,
        total_state_checks=local + global_checks, maximum_branch_parent_cell_queries=cells,
        maximum_transaction_counts=operations, proxy_seconds_per_position=proxy,
        proxy_basis='Discovery total elapsed/4200, including load; conservative planning proxy, not measured query latency.',
        additional_load_seconds=discovery_seconds, assumed_seconds_per_transaction=1,
        transaction_assumption='Planning allowance only; individual save/recalculate latencies not measured.',
        raw_model_seconds=round(model, 4), safety_multiplier=1.25, estimated_with_margin_seconds=with_margin,
        parent_reported_context='six19370 before+load approximately600s; user-reported context, not independently timed here.',
        uncertainty='No phase-level timings available; slow UI/recalculation or contention can still exceed the cap.',
        dve_timeout_seconds=DVE_SECONDS, kill_grace_seconds=15, watchdog_seconds=WATCHDOG_SECONDS,
        maximum_workflow_planning_seconds=MAX_WORKFLOW_SECONDS,
        reserve_after_dve_seconds=MAX_WORKFLOW_SECONDS - DVE_SECONDS,
        one_dve_session=True, reload_on_timeout=False, final_application_approval=False)


def prepare(previous, output):
    require(previous.parent == output.parent == batch.product.OUT and not output.exists(), 'Fresh successor directory required')
    old_path = previous / 'batch-plan.json'
    old = json.loads(old_path.read_bytes())
    batch.product.check_pins(json.loads((previous / 'batch-plan.sha256.json').read_bytes()))
    batch.product.check_pins(old['pins'])
    require(not (previous / 'reviewed-start.json').exists() and not (previous / 'launch.json').exists(),
            'Previous batch already started; never arrange a second session')
    discovery = Path(old['environment']['LZC_SELECTOR_NATIVE_PRODUCT_SELECTION']).parent
    status_path = discovery / 'discovery-status.json'
    status = json.loads(status_path.read_bytes())
    require(status['status'] == 'READONLY_DISCOVERY_COMPLETE_PENDING_OFFLINE_BINDING', 'Completed discovery timing required')
    budget = estimate(old, status['elapsed_seconds'])
    original_write = batch.write

    def successor_write(path, value):
        if path.name == 'batch-plan.json':
            require(value['targets'] == old['targets'] and value['protection_rows'] == old['protection_rows'],
                    'Timing successor must preserve all120 inputs/parameters/selectors/protection rows')
            require(value['command'] == old['command'] and value['command'][2] == '1200s',
                    'Original reviewed command drift')
            value['command'] = list(value['command'])
            value['command'][2] = str(DVE_SECONDS) + 's'
            value['timing_successor'] = dict(previous=str(previous), old_timeout_seconds=1200,
                budget=budget, immutable_script_sha256=sha(batch.SCRIPT), measurement_only=True)
            for pin in (old_path, previous / 'batch-plan.sha256.json', status_path, Path(__file__).resolve(),
                        HERE / 'test_lzc_selector_native_product_batch_budget.py', output / 'budget-review.json'):
                value['pins'][str(pin)] = sha(pin)
        original_write(path, value)

    # The original prepare writes each file once; intercept only the fresh plan before its seal.
    def writer(path, value):
        if path.name == 'selection.tcl':
            original_write(output / 'budget-review.json', budget)
        successor_write(path, value)

    batch.write = writer
    try:
        batch.prepare(Path(old['source_plan']), discovery, output)
    finally:
        batch.write = original_write


def reviewed_plan(output):
    require(output.parent == batch.product.OUT, 'Independent batch directory required')
    plan = json.loads((output / 'batch-plan.json').read_bytes())
    batch.product.check_pins(json.loads((output / 'batch-plan.sha256.json').read_bytes()))
    batch.product.check_pins(plan['pins'])
    require(plan['command'] == ['timeout', '--kill-after=15s', '10500s', 'xvfb-run', '-a', 'dve',
                               '-full64', '-cov', '-script', str(batch.SCRIPT)] and
            plan['timing_successor']['budget']['watchdog_seconds'] == WATCHDOG_SECONDS and
            plan['parent_review_start_required'] and not plan['application_approval'],
            'Exact sealed bounded timing-only successor required')
    return plan


def background(output):
    reviewed_plan(output)
    require(not (output / 'reviewed-start.json').exists() and not (output / 'launch.json').exists(),
            'Batch already started; no repeat session/load')
    write(output / 'reviewed-start.json', dict(status='PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED',
        batch_plan_sha256=sha(output / 'batch-plan.json'), final_application_approval=False))
    command = [sys.executable, str(Path(__file__).resolve()), 'run-reviewed-measurement', '--output', str(output)]
    with (output / 'worker.log').open('x') as log:
        worker = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, start_new_session=True)
    write(output / 'background-supervisor.json', dict(worker_pid=worker.pid, command=command, cwd=str(output),
        one_dve_load=True, bounded_seconds=DVE_SECONDS, watchdog_seconds=WATCHDOG_SECONDS,
        final_application_approval=False))
    print(json.dumps(dict(worker_pid=worker.pid, output=str(output), one_dve_load=True)))


def run(output):
    plan = reviewed_plan(output)
    start = json.loads((output / 'reviewed-start.json').read_bytes())
    require(start['status'] == 'PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED' and
            start['batch_plan_sha256'] == sha(output / 'batch-plan.json'), 'Parent-reviewed start required')
    env = dict(os.environ, **plan['environment'])
    for name in tuple(env):
        if name in ('DVE_REVIEWED_WAIVERS', 'DVE_COVERAGE_OUTPUT') or name.startswith('LZC_') and name not in plan['environment']:
            del env[name]
    started = time.monotonic()
    status = dict(status='RUNNING_SINGLETON_MEASUREMENT', final_application_approval=False,
                  license_configuration_changed=False, dve_timeout_seconds=DVE_SECONDS,
                  watchdog_seconds=WATCHDOG_SECONDS, reload_on_timeout=False)
    try:
        with (output / 'dve.log').open('x') as log:
            process = subprocess.Popen(plan['command'], cwd=output, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            write(output / 'launch.json', dict(wrapper_pid=process.pid, command=plan['command'], cwd=str(output)))
            print(json.dumps(dict(wrapper_pid=process.pid, cwd=str(output))), flush=True)
            code = process.wait(timeout=WATCHDOG_SECONDS)
        status['returncode'] = code
        require(code == 0, 'Bounded measurement did not exit normally; record failure, no retry/load')
        batch.product.check_pins(plan['pins'])
        result = batch.verify(output, plan)
        result['input_sha256'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
        write(output / 'batch-result.json', result)
        write(output / 'batch-result.sha256.json', {str(output / 'batch-result.json'): sha(output / 'batch-result.json')})
        status['status'] = result['status']
        print(json.dumps({k: result[k] for k in ('status', 'native_signature_qualified_candidates', 'counts', 'branch_hold')}))
    except Exception as error:
        if 'process' in locals() and process.poll() is None:
            os.killpg(process.pid, 15)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, 9)
                process.wait()
        status.update(status='FAILED_RECORDED_NOT_QUALIFICATION', error=str(error))
        raise
    finally:
        status['elapsed_seconds'] = round(time.monotonic() - started, 3)
        status['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
        write(output / 'batch-status.json', status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--previous', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    for mode in ('launch-background-reviewed', 'run-reviewed-measurement'):
        command = commands.add_parser(mode)
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.previous.resolve(), args.output.resolve())
    elif args.mode == 'launch-background-reviewed':
        background(args.output.resolve())
    else:
        run(args.output.resolve())


if __name__ == '__main__':
    main()
