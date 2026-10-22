#!/usr/bin/env python3
"""Seal batch05 and a separate temporary singleton smoke; only smoke launch is exposed."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import lzc_selector_native_product_batch_v4 as v4
from lzc_selector_native_prepare import require, sha, write, tcl_word

batch = v4.batch
HERE = Path(__file__).resolve().parent
FULL = HERE / 'lzc_selector_native_product_batch_v5.tcl'
LIBRARY = HERE / 'lzc_selector_native_product_batch_v5_library.tcl'
PROBE = HERE / 'lzc_selector_native_product_guard_smoke.tcl'
GUARD = HERE / 'lzc_selector_native_product_guard_legacy.tcl'


def dependency_scan(files):
    result = {}
    for path in files:
        require('{*}' not in path.read_text(), 'Unsupported expansion in actual dependency: ' + str(path))
        result[str(path)] = sha(path)
    return result


def prepare(previous, review, output, probe):
    require(all(p.parent == batch.product.OUT for p in (previous, review, output, probe)) and
            output != probe and not output.exists() and not probe.exists(), 'Fresh separate prepare/probe directories required')
    old = v4.reviewed_plan(previous)
    batch.product.check_pins(json.loads((review / 'terminal-review.sha256.json').read_bytes()))
    terminal = json.loads((review / 'terminal-review.json').read_bytes())
    batch.product.check_pins(terminal['pins'])
    require(terminal['batch'] == str(previous) and terminal['native_signature_qualified_candidates'] == 0 and
            terminal['protected_state_differences'] == [] and terminal['audit_rows'] ==
            {'global-before': 4200, 'global-final': 4200, 'case-000-before': 84}, 'Exact terminal rejection/protection review required')
    discovery = Path(old['environment']['LZC_SELECTOR_NATIVE_PRODUCT_SELECTION']).parent
    original_write = batch.write

    def writer(path, value):
        if path.name == 'selection.tcl':
            require(value.partition('\n')[2] == (previous / 'selection.tcl').read_text().partition('\n')[2], 'Sealed selection drift')
            original_write(output / 'native-bindings.tcl', (previous / 'native-bindings.tcl').read_text())
            original_write(output / 'guarded-session.tcl', (previous / 'guarded-session.tcl').read_text())
            original_write(output / 'budget-review.json', (previous / 'budget-review.json').read_text())
        if path.name == 'batch-plan.json':
            require(value['targets'] == old['targets'] and value['protection_rows'] == old['protection_rows'], '120/4200 population drift')
            value['command'] = list(old['command'])
            value['command'][-1] = str(FULL)
            value['environment'].update(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS=str(output / 'native-bindings.tcl'),
                LZC_SELECTOR_NATIVE_GUARDED_SESSION=str(output / 'guarded-session.tcl'))
            deps = [FULL, LIBRARY, PROBE, GUARD, v4.v3.visibility.SCRIPT, batch.SCRIPT,
                    HERE / 'lzc_selector_native_product_discover.tcl', discovery / 'selection.tcl',
                    output / 'selection.tcl', output / 'native-bindings.tcl', output / 'guarded-session.tcl']
            scan = dependency_scan(deps)
            value['legacy_guard_successor'] = dict(previous=str(previous), terminal_review=str(review),
                actual_script_sha256=sha(FULL), actual_entry_dependency_pins=scan,
                unsupported_expansion_occurrences=0, historical_v3_v4_entries_not_loaded=True,
                old_global_before_context_only=True, same_session_global4200_gate_required=True,
                short_probe_first_parent_review_required=True, full_batch_launch_not_exposed=True,
                watchdog_seconds=10530, actual_runtime_patchlevel_pending=True)
            value['pins'].update(old['pins'])
            value['pins'].update(scan)
            for pin in (previous / 'batch-plan.json', previous / 'batch-plan.sha256.json',
                        review / 'terminal-review.json', review / 'terminal-review.sha256.json',
                        Path(__file__).resolve(), HERE / 'test_lzc_selector_native_product_batch_v5_prepare.py',
                        HERE / 'test_lzc_selector_native_product_guard_legacy.py',
                        HERE / 'test_lzc_selector_native_product_guard_smoke.py', output / 'budget-review.json'):
                value['pins'][str(pin)] = sha(pin)
        original_write(path, value)

    batch.write = writer
    try:
        batch.prepare(Path(old['source_plan']), discovery, output)
    finally:
        batch.write = original_write
    probe.mkdir()
    scope = old['targets'][0]['candidate']['scope']
    local = [r for r in old['protection_rows'] if r['scope'] == scope]
    require(len(local) == 84, 'Exact case000 child scope required')
    write(probe / 'probe-selection.tcl', 'set lpq_scope ' + tcl_word(scope) + '\nset lpq_output ' + tcl_word(probe) + '\n')
    full = v4.v3.sealed(output, 'batch-plan')
    pins = dict(full['pins'])
    for pin in (output / 'batch-plan.json', output / 'batch-plan.sha256.json', probe / 'probe-selection.tcl'):
        pins[str(pin)] = sha(pin)
    deps = dict(full['legacy_guard_successor']['actual_entry_dependency_pins'])
    deps.update(dependency_scan([probe / 'probe-selection.tcl']))
    record = dict(status='PREPARED_TEMPORARY_SINGLETON_SMOKE_PARENT_REVIEW_REQUIRED_NOT_QUALIFICATION', full_prepare=str(output),
        command=['timeout', '--kill-after=15s', '900s', 'xvfb-run', '-a', 'dve', '-full64', '-cov', '-script', str(PROBE)],
        environment=dict(full['environment'], LZC_SELECTOR_NATIVE_PROBE_SELECTION=str(probe / 'probe-selection.tcl')),
        scope=scope, module_checksum='3250293308', positions=84, branch_positions=24, condition_positions=60,
        same_session_scope_audits=5, global4200_fresh_audit=False, qualification_gate_remains_closed=True,
        original_global_before=str(previous / 'global-before.tsv'), historical_baseline_context_only=True,
        actual_entry_dependency_pins=deps, watchdog_seconds=930, retry=False, one_dve_load=True,
        estimated_budget_basis='Discovery03 measured277.34s for36 children/4200 positions incl load;900s bounded allowance for one84-position child/5audits/reset/reload, not measured smoke latency.',
        capture=True, exclusion=True, temporary_singleton_points=1, final_reset_required=True,
        measurement_only=True, target=old['targets'][0],
        application_approval=False, qualified_candidates=0,
        parent_review_start_required=True, pins=pins)
    write(probe / 'smoke-plan.json', record)
    write(probe / 'smoke-plan.sha256.json', {str(probe / 'smoke-plan.json'): sha(probe / 'smoke-plan.json')})
    reviewed_probe(probe)
    print(json.dumps(dict(full_prepare=str(output), temporary_singleton_smoke=str(probe), launched=False)))


def reviewed_probe(output):
    require(output.parent == batch.product.OUT, 'Independent probe output required')
    plan = v4.v3.sealed(output, 'smoke-plan')
    full = v4.v3.sealed(Path(plan['full_prepare']), 'batch-plan')
    require(plan['command'] == ['timeout', '--kill-after=15s', '900s', 'xvfb-run', '-a', 'dve',
                               '-full64', '-cov', '-script', str(PROBE)] and
            plan['environment'] == dict(full['environment'], LZC_SELECTOR_NATIVE_PROBE_SELECTION=str(output / 'probe-selection.tcl')) and
            plan['positions'] == 84 and plan['watchdog_seconds'] == 930 and plan['qualification_gate_remains_closed'] and
            plan['same_session_scope_audits'] == 5 and
            not plan['global4200_fresh_audit'] and plan['capture'] and plan['exclusion'] and plan['measurement_only'] and
            plan['temporary_singleton_points'] == 1 and plan['final_reset_required'] and
            not plan['application_approval'] and not plan['retry'] and plan['parent_review_start_required'],
            'Exact reviewed temporary singleton smoke contract required')
    dependency_scan([Path(p) for p in plan['actual_entry_dependency_pins']])
    old = v4.reviewed_plan(Path(full['legacy_guard_successor']['previous']))
    require(full['targets'] == old['targets'] and full['protection_rows'] == old['protection_rows'] and
            full['command'] == old['command'][:-1] + [str(FULL)], 'Full successor population/budget drift')
    require(plan['target'] == full['targets'][0] and plan['scope'] == plan['target']['candidate']['scope'], 'Smoke target drift')
    return plan, full


def verify_probe(output, plan, full):
    gui = (output / 'DVEfiles/dve_gui.log').read_text()
    require(gui.count('LZC_NATIVE_GUARD_SMOKE_COMPLETE_PENDING_OFFLINE_VERIFICATION_NOT_QUALIFICATION') == 1 and
            gui.count('LZC_NATIVE_SMOKE_GUARD_PREFLIGHT_COMPLETE_GATE_CLOSED_NO_NATIVE_CALL') == 1 and
            'LZC_NATIVE_GUARD_SMOKE_FAILED' not in gui and 'LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE' not in gui,
            'Short smoke failed or incorrectly opened qualification gate')
    version = re.findall(r'LZC_NATIVE_GUARD_PREFLIGHT_COMPLETE patchlevel=(\S+) payloads=5 gate=closed no_native_call', gui)
    require(len(version) == 1, 'Actual runtime preflight evidence required')
    rows = full['protection_rows']
    binding = batch.capture.bind_signature((output / 'first.el').read_bytes(), (output / 'second.el').read_bytes(),
                                           plan['target']['candidate'], rows, [])
    for stage, active in (('before', -1), ('selected', binding['position']), ('reset', -1),
                          ('reloaded', binding['position']), ('final', -1)):
        require(batch.audit(output / (stage + '.tsv'), rows, active, plan['scope']) == 84, 'Scope protection count drift')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((output / name).read_bytes() == b'', 'Smoke native reset exclusion not empty')
    require({p.name for p in output.glob('*.el')} == {'initial-empty.el', 'reset-empty.el', 'final-empty.el', 'first.el', 'second.el'}, 'Unexpected smoke EL')
    return dict(status='TEMPORARY_SINGLETON_SMOKE_VERIFIED_NOT_FULL_QUALIFICATION',
        runtime_patchlevel=version[0], literal_annotation_payloads_checked=5, fresh_scope_positions=84,
        same_session_scope_audits=5, singleton_binding=binding, final_reset_empty=True,
        protected_state_changes=[dict(stage=s, position=binding['position']) for s in ('selected', 'reloaded')],
        global4200_same_session_qualification=False, capture=True,
        qualified_candidates=0, actual_processor_waivers_added=0, application_approval=False)


def background(output):
    reviewed_probe(output)
    require(not (output / 'reviewed-start.json').exists() and not (output / 'launch.json').exists(), 'No repeat probe session')
    write(output / 'reviewed-start.json', dict(smoke_plan_sha256=sha(output / 'smoke-plan.json'), measurement_only=True))
    command = [sys.executable, str(Path(__file__).resolve()), 'run-reviewed-smoke', '--output', str(output)]
    with (output / 'worker.log').open('x') as log:
        worker = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    write(output / 'background-supervisor.json', dict(worker_pid=worker.pid, command=command, measurement_only=True, one_dve_load=True))
    print(json.dumps(dict(worker_pid=worker.pid, output=str(output), measurement_only=True)))


def run(output):
    plan, full = reviewed_probe(output)
    require(json.loads((output / 'reviewed-start.json').read_bytes())['smoke_plan_sha256'] == sha(output / 'smoke-plan.json') and
            not (output / 'launch.json').exists(), 'Unique parent-reviewed probe start required')
    env = dict(os.environ, **plan['environment'])
    for name in tuple(env):
        if name in ('DVE_REVIEWED_WAIVERS', 'DVE_COVERAGE_OUTPUT') or name.startswith('LZC_') and name not in plan['environment']:
            del env[name]
    started = time.monotonic()
    status = dict(status='RUNNING_TEMPORARY_SINGLETON_SMOKE_NOT_QUALIFICATION', application_approval=False)
    try:
        with (output / 'dve.log').open('x') as log:
            process = subprocess.Popen(plan['command'], cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            write(output / 'launch.json', dict(wrapper_pid=process.pid, command=plan['command'], actual_script_sha256=sha(PROBE)))
            status['returncode'] = process.wait(timeout=930)
        require(status['returncode'] == 0, 'Probe exit failed; no retry')
        reviewed_probe(output)
        result = verify_probe(output, plan, full)
        result['pins'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
        write(output / 'smoke-result.json', result)
        write(output / 'smoke-result.sha256.json', {str(output / 'smoke-result.json'): sha(output / 'smoke-result.json')})
        status['status'] = result['status']
    except Exception as error:
        if 'process' in locals() and process.poll() is None:
            os.killpg(process.pid, 15)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, 9)
                process.wait()
        status.update(status='FAILED_RECORDED_NOT_QUALIFICATION', error=str(error))
        raise
    finally:
        status['elapsed_seconds'] = round(time.monotonic() - started, 3)
        write(output / 'smoke-status.json', status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    for name in ('previous', 'review', 'output', 'probe-output'):
        prep.add_argument('--' + name, type=Path, required=True)
    for mode in ('launch-background-reviewed-smoke', 'run-reviewed-smoke'):
        commands.add_parser(mode).add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.previous.resolve(), args.review.resolve(), args.output.resolve(), args.probe_output.resolve())
    elif args.mode == 'launch-background-reviewed-smoke': background(args.output.resolve())
    else: run(args.output.resolve())


if __name__ == '__main__':
    main()
