#!/usr/bin/env python3
"""Add a smoke-gated launch entry to sealed full05; never reprepare its inputs."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType

import lzc_selector_native_product_batch_v4 as v4
import lzc_selector_native_product_batch_v5_prepare as v5
from lzc_selector_native_prepare import require, sha, write

HERE = Path(__file__).resolve().parent


def verified_inputs(output, smoke):
    smoke_plan, full = v5.reviewed_probe(smoke)
    require(output == Path(smoke_plan['full_prepare']), 'Smoke must bind exactly this sealed full05')
    saved = v4.v3.sealed(smoke, 'smoke-result')
    status = json.loads((smoke / 'smoke-status.json').read_bytes())
    measured = v5.verify_probe(smoke, smoke_plan, full)
    require({k: saved[k] for k in measured} == measured and
            status['status'] == measured['status'] and status['returncode'] == 0 and
            measured['final_reset_empty'] and measured['same_session_scope_audits'] == 5 and
            measured['fresh_scope_positions'] == 84 and measured['qualified_candidates'] == 0 and
            not measured['global4200_same_session_qualification'] and not measured['application_approval'],
            'Sealed actual smoke/reset verification required, not qualification or historical coverage')
    require(len(full['targets']) == 120 and len(full['protection_rows']) == 4200 and
            full['command'] == ['timeout', '--kill-after=15s', '10500s', 'xvfb-run', '-a', 'dve',
                                '-full64', '-cov', '-script', str(v5.FULL)] and
            full['legacy_guard_successor']['watchdog_seconds'] == 10530 and
            full['legacy_guard_successor']['same_session_global4200_gate_required'] and
            full['parent_review_start_required'] and not full['application_approval'], 'Exact sealed full05 contract required')
    return full, measured, saved


def prepare(output, smoke):
    require(output.parent == smoke.parent == v4.batch.product.OUT and
            not (output / 'full-launch-plan.json').exists() and
            not (output / 'reviewed-start.json').exists() and not (output / 'launch.json').exists(),
            'Fresh additive launch contract for unstarted full05 required')
    full, measured, saved = verified_inputs(output, smoke)
    pins = dict(full['pins'])
    pins.update(saved['pins'])
    for pin in (output / 'batch-plan.json', output / 'batch-plan.sha256.json',
                smoke / 'smoke-result.json', smoke / 'smoke-result.sha256.json', smoke / 'smoke-status.json',
                Path(__file__).resolve(), HERE / 'test_lzc_selector_native_product_batch_v5_launch.py',
                Path(v4.__file__).resolve(), Path(v5.__file__).resolve()):
        pins[str(pin)] = sha(pin)
    record = dict(status='PREPARED_FULL05_LAUNCH_ENTRY_PARENT_REVIEW_REQUIRED_NOT_PROCESSOR_APPLICATION',
        output=str(output), smoke=str(smoke), batch_plan_sha256=sha(output / 'batch-plan.json'),
        actual_dve_command=full['command'], actual_script_sha256=sha(v5.FULL),
        lifecycle_source=str(Path(v4.__file__).resolve()), lifecycle_source_sha256=sha(Path(v4.__file__)),
        lifecycle_methods=['background', 'run'], isolated_dependency_binding=True,
        runtime_patchlevel=measured['runtime_patchlevel'], smoke_singleton_binding=measured['singleton_binding'],
        smoke_proof_role='Prerequisite parser/native-call/reset compatibility only; no IDs transferred into full05 and no qualification credit.',
        targets=120, protected_positions=4200, batch_inputs_reprepared=False,
        same_session_full_protection_required=True, dve_timeout_seconds=10500, watchdog_seconds=10530,
        retry=False, one_dve_load=True, parent_review_start_required=True,
        application_approval=False, actual_processor_waivers_added=0, pins=pins)
    write(output / 'full-launch-plan.json', record)
    write(output / 'full-launch-plan.sha256.json', {str(output / 'full-launch-plan.json'): sha(output / 'full-launch-plan.json')})
    reviewed_plan(output)
    print(json.dumps(dict(status=record['status'], output=str(output), launched=False)))


def reviewed_plan(output):
    require(output.parent == v4.batch.product.OUT, 'Exact full output boundary required')
    contract = v4.v3.sealed(output, 'full-launch-plan')
    full, measured, _ = verified_inputs(output, Path(contract['smoke']))
    require(contract['output'] == str(output) and contract['batch_plan_sha256'] == sha(output / 'batch-plan.json') and
            contract['actual_dve_command'] == full['command'] and contract['actual_script_sha256'] == sha(v5.FULL) and
            contract['lifecycle_source_sha256'] == sha(Path(v4.__file__)) and
            contract['runtime_patchlevel'] == measured['runtime_patchlevel'] and
            contract['smoke_singleton_binding'] == measured['singleton_binding'] and
            contract['targets'] == 120 and contract['protected_positions'] == 4200 and
            contract['dve_timeout_seconds'] == 10500 and contract['watchdog_seconds'] == 10530 and
            contract['same_session_full_protection_required'] and not contract['batch_inputs_reprepared'] and
            contract['one_dve_load'] and not contract['retry'] and contract['parent_review_start_required'] and
            not contract['application_approval'], 'Exact smoke-gated full05 launch contract required')
    return full


def verify(output, plan):
    result = v4.batch.verify(output, plan)
    gui = (output / 'DVEfiles/dve_gui.log').read_text()
    versions = re.findall(r'LZC_NATIVE_GUARD_PREFLIGHT_COMPLETE patchlevel=(\S+) payloads=5 gate=closed no_native_call', gui)
    contract = v4.v3.sealed(output, 'full-launch-plan')
    require(gui.count('LZC_NATIVE_BATCH_V5_LEGACY_GUARD_SESSION_LOADED') == 1 and
            gui.count('LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE') == 1 and
            versions == [contract['runtime_patchlevel']], 'Actual v5 runtime/entry/full same-session gate evidence required')
    result.update(actual_script_sha256=sha(v5.FULL), runtime_patchlevel=versions[0],
                  smoke_used_as_full_protection=False, final_application_approval=False)
    return result


def lifecycle(name):
    # Reuse frozen code with private globals; never mutate the frozen module.
    frozen = getattr(v4, name)
    bindings = dict(frozen.__globals__, SCRIPT=v5.FULL, reviewed_plan=reviewed_plan,
                    verify=verify, __file__=str(Path(__file__).resolve()))
    return FunctionType(frozen.__code__, bindings, frozen.__name__, frozen.__defaults__, frozen.__closure__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare-launch-entry')
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--smoke', type=Path, required=True)
    for mode in ('launch-background-reviewed', 'run-reviewed-measurement'):
        commands.add_parser(mode).add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare-launch-entry':
        prepare(args.output.resolve(), args.smoke.resolve())
    else:
        lifecycle('background' if args.mode == 'launch-background-reviewed' else 'run')(args.output.resolve())


if __name__ == '__main__':
    main()
