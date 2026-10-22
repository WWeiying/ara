#!/usr/bin/env python3
"""One bounded native singleton batch; resets all exclusions, never final application."""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lzc_selector_native_prepare import require, sha, write, tcl_word
import lzc_selector_native_product_prepare as product
import lzc_selector_native_product_capture_prepare as capture
from lzc_selector_native_product_inventory import decode_lines

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'lzc_selector_native_product_batch.tcl'


def prepare(source_plan, discovery, output):
    require(output.parent == product.OUT and not output.exists(), 'Fresh independent batch directory required')
    product.check_pins(json.loads(source_plan.with_suffix('.sha256.json').read_bytes()))
    parent = json.loads(source_plan.read_bytes())
    product.check_pins(parent['pins'])
    require(parent['candidates'] == 120 and not parent['application_approval'], '120 source-bound candidates required')
    targets = sorted(parent['targets'], key=lambda t: (t['candidate']['metric'] != 'cond', t['candidate']['key']))
    output.mkdir()
    rows = parent['protection_rows']
    text = 'set lpb_output ' + tcl_word(output) + '\nset lpb_rows [list \\\n'
    for i, r in enumerate(rows):
        values = (r['scope'], r['metric'], r['native_id'] or '', r['expression'] or '', r['vector'], i)
        text += ' [list ' + ' '.join(map(tcl_word, values)) + '] \\\n'
    text += ']\nset lpb_targets [list \\\n'
    experiments = []
    for i, t in enumerate(targets):
        c = t['candidate']
        product.eligible(c['xml_provenance'], c['parameters']['WIDTH'], c['metric'])
        values = (i, c['key'], c['scope'], c['metric'], c['expression'], c['metric_checksum'],
                  c['point_checksum'], t['target_position'] if t['target_position'] is not None else -1)
        text += ' [list ' + ' '.join(map(tcl_word, values)) + '] \\\n'
        experiments.append(dict(number=i, candidate=c))
    text += ']\n'
    write(output / 'selection.tcl', text)
    pins = dict(parent['pins'])
    for path in (source_plan, source_plan.with_suffix('.sha256.json'), discovery / 'selection.tcl', SCRIPT,
                 HERE / 'lzc_selector_native_product_discover.tcl', Path(__file__).resolve(),
                 HERE / 'test_lzc_selector_native_product_batch.py', output / 'selection.tcl'):
        pins[str(path)] = sha(path)
    record = dict(status='PREPARED_SINGLE_SESSION_PARENT_REVIEW_REQUIRED_SINGLETON_MEASUREMENT_ONLY',
        targets=experiments, protection_rows=rows, pins=pins,
        command=['timeout', '--kill-after=15s', '1200s', 'xvfb-run', '-a', 'dve', '-full64', '-cov',
                 '-script', str(SCRIPT)],
        environment={'LZC_SELECTOR_NATIVE_PRODUCT_SELECTION': str(discovery / 'selection.tcl'),
                     'LZC_SELECTOR_NATIVE_BATCH_SELECTION': str(output / 'selection.tcl')},
        proof='Global before/final4200 queries; each target child5 audits; every saved global EL exactly singleton and every reset global EL empty.',
        branch_policy='Exact native parent text only; unbound branch HOLD without exclusion; no XML/root numeric fallback.',
        parent_review_start_required=True, application_approval=False,
        license_configuration_changed=False, op16='HOLD', source_plan=str(source_plan))
    write(output / 'batch-plan.json', record)
    write(output / 'batch-plan.sha256.json', {str(output / 'batch-plan.json'): sha(output / 'batch-plan.json')})
    print(json.dumps(dict(status=record['status'], output=str(output), targets=120)))


def audit(path, rows, active, scope=None):
    with path.open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['position', 'scope', 'metric', 'native_id', 'expression', 'vector', 'excluded'],
                'Unexpected protection audit schema')
        actual = list(reader)
    expected = [dict(position=str(i), scope=r['scope'], metric=r['metric'], native_id=r['native_id'] or '',
                     expression=r['expression'] or '', vector=r['vector'], excluded=str(int(i == active)))
                for i, r in enumerate(rows) if scope is None or r['scope'] == scope]
    require(actual == expected, 'Native protected state differs: ' + str(path))
    return len(expected)


def branch_observations(case, c):
    records = decode_lines((case / 'branch-parents.tcllist').read_bytes().decode('latin1'))
    bindings = [r for r in records if r[0] == 'binding']
    require(len(bindings) == 1, 'Unique exact branch expression observation required')
    _, scope, identity, expression = bindings[0]
    require(scope == c['scope'] and expression == c['expression'], 'Branch raw expression binding differs')
    parents = [r for r in records if r[0] == 'parent' and r[1] == scope and r[2] == 'Item' + identity]
    require(len(parents) == 1, 'Missing independent native branch parent evidence')
    import tkinter
    parser = tkinter.Tcl()
    cells = [parser.splitlist(v) for v in parser.splitlist(parents[0][3])]
    require(any(len(cell) == 3 and cell[1] == '0' and cell[2] == expression for cell in cells),
            'Native branch binding not backed by exact parent text')
    return [dict(scope=scope, native_id=identity, expression=expression, raw_parent_text=expression,
                 expression_source='native_parent_text', module_checksum=c['module_checksum'],
                 parent_path='Item' + identity, arms=['0', '1'])]


def verify(output, plan):
    rows = plan['protection_rows']
    checks = audit(output / 'global-before.tsv', rows, -1) + audit(output / 'global-final.tsv', rows, -1)
    require((output / 'initial-empty.el').read_bytes() == (output / 'final-empty.el').read_bytes() == b'',
            'Global batch initial/final state not empty')
    log = (output / 'DVEfiles/dve_gui.log').read_text()
    require('LZC_NATIVE_BATCH_COMPLETE_PENDING_OFFLINE_VERIFICATION' in log and
            'LZC_NATIVE_BATCH_FAILED' not in log, 'Batch not completed/reset')
    results, holds = [], []
    for target in plan['targets']:
        number, c = target['number'], target['candidate']
        case = output / f'case-{number:03d}'
        marker = f'LZC_NATIVE_BATCH_SINGLETON_COMPLETE {number} position='
        if marker not in log:
            require(c['metric'] == 'branch' and f'LZC_NATIVE_BATCH_HOLD {number} ' in log and
                    not list(case.glob('*.el')), 'Unexplained missing capture')
            holds.append(dict(candidate=c, reason='Exact native branch parent expression not available'))
            continue
        require(log.count(marker) == 1, 'Repeated singleton completion marker')
        observations = branch_observations(case, c) if c['metric'] == 'branch' else []
        result = capture.bind_signature((case / 'first.el').read_bytes(), (case / 'second.el').read_bytes(),
                                        c, rows, observations)
        for stage, active in (('before', -1), ('selected', result['position']), ('reset', -1),
                              ('reloaded', result['position']), ('final', -1)):
            checks += audit(case / (stage + '.tsv'), rows, active, c['scope'])
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
            require((case / name).read_bytes() == b'', 'Residual global reset exclusions')
        require({p.name for p in case.glob('*.el')} == {'first.el', 'second.el', 'initial-empty.el',
                                                      'reset-empty.el', 'final-empty.el'}, 'Unapproved saved EL')
        result.update(candidate=c, explicit_global_exclusion_set='Exactly this singleton in first/second EL; empty at reset',
                      native_signature_qualified=True, waiver_application_approved=False)
        results.append(result)
    return dict(status='BATCH_SINGLETON_NATIVE_SIGNATURES_VERIFIED_NOT_FINAL_WAIVER_APPLICATION',
        native_signature_qualified_candidates=len(results), counts=dict(Counter(r['candidate']['metric'] for r in results)),
        branch_hold=len(holds), holds=holds, results=results, native_position_state_checks=checks,
        global_visible_positions=4200, all_roundtrips_identical=True, global_final_empty=True,
        xml_or_root_native_ids_transferred=False, op16='HOLD', four_state_initialization_qualified=False,
        actual_effective_processor_waivers_added=0, final_application_approval=False)


def run(output):
    plan = json.loads((output / 'batch-plan.json').read_bytes())
    product.check_pins(json.loads((output / 'batch-plan.sha256.json').read_bytes()))
    product.check_pins(plan['pins'])
    start = json.loads((output / 'reviewed-start.json').read_bytes())
    require(start['status'] == 'PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED' and
            start['batch_plan_sha256'] == sha(output / 'batch-plan.json') and
            not plan['application_approval'], 'Reviewed measurement-only start required')
    env = dict(os.environ, **plan['environment'])
    for name in tuple(env):
        if name in ('DVE_REVIEWED_WAIVERS', 'DVE_COVERAGE_OUTPUT') or name.startswith('LZC_') and name not in plan['environment']:
            del env[name]
    started = time.monotonic()
    status = dict(status='RUNNING_SINGLETON_MEASUREMENT', final_application_approval=False,
                  license_configuration_changed=False)
    try:
        with (output / 'dve.log').open('x') as log:
            process = subprocess.Popen(plan['command'], cwd=output, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            write(output / 'launch.json', dict(wrapper_pid=process.pid, command=plan['command'], cwd=str(output)))
            print(json.dumps(dict(wrapper_pid=process.pid, cwd=str(output))), flush=True)
            code = process.wait(timeout=1230)
        status['returncode'] = code
        require(code == 0, 'Bounded DVE batch did not exit normally')
        product.check_pins(plan['pins'])
        result = verify(output, plan)
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


def background(output):
    require(output.parent == product.OUT, 'Independent batch directory under verification/out required')
    plan = json.loads((output / 'batch-plan.json').read_bytes())
    product.check_pins(json.loads((output / 'batch-plan.sha256.json').read_bytes()))
    product.check_pins(plan['pins'])
    require(plan['parent_review_start_required'] and not plan['application_approval'], 'Measurement only')
    require(not (output / 'reviewed-start.json').exists() and not (output / 'launch.json').exists(),
            'Batch already started; never launch another DVE into the same evidence directory')
    write(output / 'reviewed-start.json', dict(status='PARENT_REVIEWED_SINGLETON_MEASUREMENT_START_REQUESTED',
        batch_plan_sha256=sha(output / 'batch-plan.json'), final_application_approval=False))
    command = [sys.executable, str(Path(__file__).resolve()), 'run-reviewed-measurement', '--output', str(output)]
    with (output / 'worker.log').open('x') as log:
        worker = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, start_new_session=True)
    write(output / 'background-supervisor.json', dict(worker_pid=worker.pid, command=command,
        cwd=str(output), one_dve_load=True, bounded_seconds=1200, final_application_approval=False))
    print(json.dumps(dict(worker_pid=worker.pid, output=str(output), one_dve_load=True)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--source-plan', type=Path, required=True)
    prep.add_argument('--discovery', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    start = commands.add_parser('run-reviewed-measurement')
    start.add_argument('--output', type=Path, required=True)
    bg = commands.add_parser('launch-background-reviewed')
    bg.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.source_plan.resolve(), args.discovery.resolve(), args.output.resolve())
    elif args.mode == 'run-reviewed-measurement':
        run(args.output.resolve())
    else:
        background(args.output.resolve())


if __name__ == '__main__':
    main()
