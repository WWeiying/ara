#!/usr/bin/env python3
"""Builtin-preserving batch successor: prepare only unless parent explicitly starts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tkinter

import lzc_selector_native_product_batch_v3 as v3
from lzc_selector_native_prepare import require, sha, write, tcl_word

batch = v3.batch
HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'lzc_selector_native_product_batch_v4.tcl'
CALL = 'gui_exclude_items -id CovDetail.1 -list $listname -selected -annotation {Native singleton measurement only; no final processor exclusion application}'
GUARDED_CALL = CALL.replace('gui_exclude_items', 'lpn_guard_exclude', 1)


def guarded_session():
    parser = tkinter.Tcl()
    parser.eval('set lpb_test_only 1\nsource ' + tcl_word(batch.SCRIPT))
    require(parser.eval('info args lpb_session') == '', 'Frozen session argument contract changed')
    body = parser.eval('info body lpb_session')
    require(body.count(CALL) == 1 and body.count('gui_exclude_items') == 1 and
            'lpn_guard_exclude' not in body, 'Exactly one frozen native exclusion call required')
    replacement = body.replace(CALL, GUARDED_CALL, 1)
    return 'proc lpb_session {} {' + replacement + '}\n', dict(
        procedure='lpb_session', substitutions=1, old_call=CALL, new_call=GUARDED_CALL,
        all_other_body_bytes_identical=True, frozen_source=str(batch.SCRIPT),
        frozen_source_sha256=sha(batch.SCRIPT), builtin_renamed=False, builtin_redefined=False)


def prepare(previous, output):
    require(previous.parent == output.parent == batch.product.OUT and not output.exists(),
            'Fresh independent successor required')
    old = v3.reviewed_plan(previous)
    status_path = previous / 'batch-status.json'
    status = json.loads(status_path.read_bytes())
    gui_path = previous / 'DVEfiles/dve_gui.log'
    gui = gui_path.read_text()
    require(status['status'] == 'FAILED_RECORDED_NOT_QUALIFICATION' and status['returncode'] == 0 and
            'EK-CMD-013' in gui and 'command cannot be renamed' in gui and
            'rename gui_exclude_items lpn_native_exclude' in gui and
            not (previous / 'global-before.tsv').exists() and not list(previous.glob('case-*')) and
            not (previous / 'batch-result.json').exists(), 'Exact pre-session builtin-rename failure required')
    text, change = guarded_session()
    diagnosis = Path(old['visibility_successor']['diagnosis'])
    discovery = Path(old['environment']['LZC_SELECTOR_NATIVE_PRODUCT_SELECTION']).parent
    raw = v3.visibility.decode_lines((discovery / 'native-inventory.tcllist').read_bytes().decode('latin1'))
    values = v3.visibility.bindings(old['protection_rows'], raw)
    bindings = v3.visibility.selection_text(values)
    require(bindings == (previous / 'native-bindings.tcl').read_text(), 'Observed native bindings changed')
    original_write = batch.write

    def writer(path, value):
        if path.name == 'selection.tcl':
            require(value.partition('\n')[2] == (previous / 'selection.tcl').read_text().partition('\n')[2],
                    'Inputs/targets/protection selection changed')
            original_write(output / 'native-bindings.tcl', bindings)
            original_write(output / 'guarded-session.tcl', text)
            original_write(output / 'session-change.json', change)
            original_write(output / 'budget-review.json', json.loads((previous / 'budget-review.json').read_bytes()))
            original_write(output / 'failure-review.json', dict(
                failed_batch=str(previous), elapsed_seconds=status['elapsed_seconds'],
                status='STATIC_CONFIRMED_BUILTIN_RENAME_FAILURE_NOT_QUALIFIED',
                cause='Synopsys refuses rename of protected gui_exclude_items builtin (EK-CMD-013). Failure before frozen session/design load/global-before.',
                correction='Replace one call in new owned session copy with guard wrapper; wrapper calls untouched native gui_exclude_items.',
                qualified_candidates=0, launched=False, rtl_modified=False, frozen_files_modified=False,
                evidence={str(p): sha(p) for p in (status_path, gui_path)}))
        if path.name == 'batch-plan.json':
            require(value['targets'] == old['targets'] and value['protection_rows'] == old['protection_rows'],
                    'All120 targets and4200 protected rows must remain identical')
            value['command'] = list(old['command'])
            value['command'][-1] = str(SCRIPT)
            value['environment']['LZC_SELECTOR_NATIVE_AUDIT_BINDINGS'] = str(output / 'native-bindings.tcl')
            value['environment']['LZC_SELECTOR_NATIVE_GUARDED_SESSION'] = str(output / 'guarded-session.tcl')
            value['builtin_preserving_successor'] = dict(previous=str(previous), diagnosis=str(diagnosis),
                actual_script=str(SCRIPT), actual_script_sha256=sha(SCRIPT),
                library=str(v3.SCRIPT), library_sha256=sha(v3.SCRIPT),
                frozen_verifier=str(Path(batch.__file__).resolve()), frozen_verifier_sha256=sha(Path(batch.__file__)),
                guarded_session_sha256=sha(output / 'guarded-session.tcl'),
                global_before_required_positions=4200, dve_timeout_seconds=10500, watchdog_seconds=10530,
                one_dve_load=True, retry=False, measurement_only=True, builtin_renamed=False,
                builtin_redefined=False, session_call_substitutions=1)
            value['pins'].update(old['pins'])
            for pin in (previous / 'batch-plan.json', previous / 'batch-plan.sha256.json',
                        status_path, gui_path, previous / 'selection.tcl', previous / 'native-bindings.tcl',
                        previous / 'budget-review.json', SCRIPT, Path(__file__).resolve(),
                        HERE / 'test_lzc_selector_native_product_batch_v4.py',
                        output / 'selection.tcl', output / 'native-bindings.tcl', output / 'guarded-session.tcl',
                        output / 'session-change.json', output / 'budget-review.json', output / 'failure-review.json'):
                value['pins'][str(pin)] = sha(pin)
        original_write(path, value)

    batch.write = writer
    try:
        batch.prepare(Path(old['source_plan']), discovery, output)
    finally:
        batch.write = original_write
    reviewed_plan(output)


def reviewed_plan(output):
    require(output.parent == batch.product.OUT, 'Independent output required')
    plan = v3.sealed(output, 'batch-plan')
    successor = plan['builtin_preserving_successor']
    require(plan['command'] == ['timeout', '--kill-after=15s', '10500s', 'xvfb-run', '-a', 'dve',
                               '-full64', '-cov', '-script', str(SCRIPT)] and
            successor['actual_script'] == str(SCRIPT) and successor['actual_script_sha256'] == sha(SCRIPT) and
            successor['library_sha256'] == sha(v3.SCRIPT) and
            successor['frozen_verifier_sha256'] == sha(Path(batch.__file__)) and
            successor['guarded_session_sha256'] == sha(output / 'guarded-session.tcl') and
            successor['watchdog_seconds'] == 10530 and successor['global_before_required_positions'] == 4200 and
            successor['dve_timeout_seconds'] == 10500 and successor['one_dve_load'] and not successor['retry'] and
            not successor['builtin_renamed'] and not successor['builtin_redefined'] and
            successor['session_call_substitutions'] == 1 and
            plan['parent_review_start_required'] and not plan['application_approval'],
            'Exact builtin-preserving script/gate/budget contract required')
    old = v3.reviewed_plan(Path(successor['previous']))
    require(plan['targets'] == old['targets'] and plan['protection_rows'] == old['protection_rows'],
            'Successor population drift')
    require(plan['environment'] == dict(old['environment'],
        LZC_SELECTOR_NATIVE_BATCH_SELECTION=str(output / 'selection.tcl'),
        LZC_SELECTOR_NATIVE_AUDIT_BINDINGS=str(output / 'native-bindings.tcl'),
        LZC_SELECTOR_NATIVE_GUARDED_SESSION=str(output / 'guarded-session.tcl')),
        'Successor environment drift')
    text, change = guarded_session()
    require((output / 'guarded-session.tcl').read_text() == text and
            json.loads((output / 'session-change.json').read_bytes()) == change,
            'Session changes exceed single guarded call')
    require((output / 'selection.tcl').read_text().partition('\n')[2] ==
            (Path(successor['previous']) / 'selection.tcl').read_text().partition('\n')[2],
            'Selection drift')
    return plan


def background(output):
    reviewed_plan(output)
    require(not (output / 'reviewed-start.json').exists() and not (output / 'launch.json').exists(), 'No repeat session/load')
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
    require(gui.count('LZC_NATIVE_BATCH_V4_BUILTIN_PRESERVING_SESSION_LOADED') == 1 and
            gui.count('LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE') == 1,
            'Actual builtin-preserving entry/global-before gate missing or repeated')
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
    prep.add_argument('--output', type=Path, required=True)
    for mode in ('launch-background-reviewed', 'run-reviewed-measurement'):
        commands.add_parser(mode).add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.previous.resolve(), args.output.resolve())
    elif args.mode == 'launch-background-reviewed':
        background(args.output.resolve())
    else:
        run(args.output.resolve())


if __name__ == '__main__':
    main()
