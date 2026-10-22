#!/usr/bin/env python3
"""Prepare/run a reviewed visibility successor; no automatic start or final apply."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import lzc_selector_native_product_batch as batch
import lzc_selector_native_product_audit_visibility as visibility
from lzc_selector_native_prepare import require, sha, write

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'lzc_selector_native_product_batch_v3.tcl'


def sealed(directory, stem):
    batch.product.check_pins(json.loads((directory / (stem + '.sha256.json')).read_bytes()))
    record = json.loads((directory / (stem + '.json')).read_bytes())
    batch.product.check_pins(record['pins'])
    return record


def prepare(previous, diagnosis, output):
    require(previous.parent == diagnosis.parent == output.parent == batch.product.OUT and not output.exists(),
            'Fresh independent successor required')
    old = sealed(previous, 'batch-plan')
    report = sealed(diagnosis, 'diagnosis')
    status = json.loads((previous / 'batch-status.json').read_bytes())
    require(status['status'] == 'FAILED_RECORDED_NOT_QUALIFICATION' and
            report['failed_batch'] == str(previous) and not report['launched'] and
            report['qualified_candidates'] == 0, 'Exact recorded failed batch diagnosis required')
    require(old['command'] == ['timeout', '--kill-after=15s', '10500s', 'xvfb-run', '-a', 'dve',
                               '-full64', '-cov', '-script', str(batch.SCRIPT)], 'Reviewed10500 predecessor required')
    discovery = Path(old['environment']['LZC_SELECTOR_NATIVE_PRODUCT_SELECTION']).parent
    raw = visibility.decode_lines((discovery / 'native-inventory.tcllist').read_bytes().decode('latin1'))
    values = visibility.bindings(old['protection_rows'], raw)
    require(json.loads((diagnosis / 'native-bindings.json').read_bytes()) == values and
            (diagnosis / 'native-bindings.tcl').read_text() == visibility.selection_text(values),
            'Native bindings differ from independently sourced complete inventory')
    original_write = batch.write

    def writer(path, value):
        if path.name == 'selection.tcl':
            require(value.partition('\n')[2] == (previous / 'selection.tcl').read_text().partition('\n')[2],
                    'Inputs/targets/protected selection changed')
            original_write(output / 'native-bindings.tcl', visibility.selection_text(values))
            review = dict(old['timing_successor']['budget'])
            review['parent_reported_context'] = 'Parent-agent measured context: six19370 before+load approximately600s; context only, not a numeric budget input.'
            review['visibility_overhead'] = 'Per Branch action expansion plus full parent/meta validation per scope/audit pass; incremental latency unmeasured. Same10500 cap, no retry/reload on timeout.'
            original_write(output / 'budget-review.json', review)
        if path.name == 'batch-plan.json':
            require(value['targets'] == old['targets'] and value['protection_rows'] == old['protection_rows'],
                    'All120 targets and4200 protection rows must remain identical')
            value['command'] = list(old['command'])
            value['command'][-1] = str(SCRIPT)
            value['environment']['LZC_SELECTOR_NATIVE_AUDIT_BINDINGS'] = str(output / 'native-bindings.tcl')
            value['visibility_successor'] = dict(previous=str(previous), diagnosis=str(diagnosis),
                actual_script=str(SCRIPT), actual_script_sha256=sha(SCRIPT),
                library=str(visibility.SCRIPT), library_sha256=sha(visibility.SCRIPT),
                frozen_verifier=str(Path(batch.__file__).resolve()), frozen_verifier_sha256=sha(Path(batch.__file__)),
                global_before_required_positions=4200, dve_timeout_seconds=10500,
                watchdog_seconds=10530, one_dve_load=True, retry=False, measurement_only=True)
            for pin in (previous / 'batch-plan.json', previous / 'batch-plan.sha256.json',
                        previous / 'batch-status.json', previous / 'selection.tcl',
                        diagnosis / 'diagnosis.json', diagnosis / 'diagnosis.sha256.json',
                        diagnosis / 'native-bindings.json', diagnosis / 'native-bindings.tcl',
                        SCRIPT, visibility.SCRIPT, Path(visibility.__file__), Path(__file__).resolve(),
                        HERE / 'test_lzc_selector_native_product_batch_v3.py',
                        output / 'native-bindings.tcl', output / 'budget-review.json'):
                value['pins'][str(pin)] = sha(pin)
            value['pins'].update(report['pins'])
        original_write(path, value)

    batch.write = writer
    try:
        batch.prepare(Path(old['source_plan']), discovery, output)
    finally:
        batch.write = original_write
    reviewed_plan(output)


def reviewed_plan(output):
    require(output.parent == batch.product.OUT, 'Independent output required')
    plan = sealed(output, 'batch-plan')
    successor = plan['visibility_successor']
    require(plan['command'] == ['timeout', '--kill-after=15s', '10500s', 'xvfb-run', '-a', 'dve',
                               '-full64', '-cov', '-script', str(SCRIPT)] and
            successor['actual_script'] == str(SCRIPT) and successor['actual_script_sha256'] == sha(SCRIPT) and
            successor['library_sha256'] == sha(visibility.SCRIPT) and
            successor['frozen_verifier_sha256'] == sha(Path(batch.__file__)) and
            successor['watchdog_seconds'] == 10530 and successor['global_before_required_positions'] == 4200 and
            successor['one_dve_load'] and not successor['retry'] and
            plan['parent_review_start_required'] and not plan['application_approval'],
            'Exact reviewed visibility script/budget/measurement contract required')
    old = sealed(Path(successor['previous']), 'batch-plan')
    require(plan['targets'] == old['targets'] and plan['protection_rows'] == old['protection_rows'],
            'Successor population drift')
    require(plan['environment'] == dict(old['environment'],
        LZC_SELECTOR_NATIVE_BATCH_SELECTION=str(output / 'selection.tcl'),
        LZC_SELECTOR_NATIVE_AUDIT_BINDINGS=str(output / 'native-bindings.tcl')),
        'Successor environment drift')
    return plan


def background(output):
    reviewed_plan(output)
    require(not (output / 'reviewed-start.json').exists() and not (output / 'launch.json').exists(),
            'No repeat session/load')
    write(output / 'reviewed-start.json', dict(status='PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED',
        batch_plan_sha256=sha(output / 'batch-plan.json'), final_application_approval=False))
    command = [sys.executable, str(Path(__file__).resolve()), 'run-reviewed-measurement', '--output', str(output)]
    with (output / 'worker.log').open('x') as log:
        worker = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, start_new_session=True)
    write(output / 'background-supervisor.json', dict(worker_pid=worker.pid, command=command,
        cwd=str(output), one_dve_load=True, bounded_seconds=10500, watchdog_seconds=10530,
        final_application_approval=False))
    print(json.dumps(dict(worker_pid=worker.pid, output=str(output), one_dve_load=True)))


def verify(output, plan):
    result = batch.verify(output, plan)
    gui = (output / 'DVEfiles/dve_gui.log').read_text()
    require(gui.count('LZC_NATIVE_BATCH_V3_VISIBILITY_BINDINGS_LOADED') == 1 and
            gui.count('LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE') == 1,
            'Actual successor identity/global-before gate missing or repeated')
    result['actual_script_sha256'] = sha(SCRIPT)
    return result


def run(output):
    plan = reviewed_plan(output)
    start = json.loads((output / 'reviewed-start.json').read_bytes())
    require(start['status'] == 'PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED' and
            start['batch_plan_sha256'] == sha(output / 'batch-plan.json') and not (output / 'launch.json').exists(),
            'Parent-reviewed unique start required')
    env = dict(os.environ, **plan['environment'])
    for name in tuple(env):
        if name in ('DVE_REVIEWED_WAIVERS', 'DVE_COVERAGE_OUTPUT') or name.startswith('LZC_') and name not in plan['environment']:
            del env[name]
    started = time.monotonic()
    status = dict(status='RUNNING_SINGLETON_MEASUREMENT', final_application_approval=False,
        license_configuration_changed=False, dve_timeout_seconds=10500, watchdog_seconds=10530,
        actual_script=str(SCRIPT), actual_script_sha256=sha(SCRIPT), reload_on_timeout=False)
    try:
        with (output / 'dve.log').open('x') as log:
            process = subprocess.Popen(plan['command'], cwd=output, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            write(output / 'launch.json', dict(wrapper_pid=process.pid, command=plan['command'], cwd=str(output),
                actual_script_sha256=sha(SCRIPT)))
            print(json.dumps(dict(wrapper_pid=process.pid, cwd=str(output))), flush=True)
            status['returncode'] = process.wait(timeout=10530)
        require(status['returncode'] == 0, 'Bounded measurement failed; no retry/load')
        reviewed_plan(output)
        result = verify(output, plan)
        result['input_sha256'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
        write(output / 'batch-result.json', result)
        write(output / 'batch-result.sha256.json', {str(output / 'batch-result.json'): sha(output / 'batch-result.json')})
        status['status'] = result['status']
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
    prep.add_argument('--diagnosis', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    for mode in ('launch-background-reviewed', 'run-reviewed-measurement'):
        commands.add_parser(mode).add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.previous.resolve(), args.diagnosis.resolve(), args.output.resolve())
    elif args.mode == 'launch-background-reviewed':
        background(args.output.resolve())
    else:
        run(args.output.resolve())


if __name__ == '__main__':
    main()
