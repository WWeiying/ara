#!/usr/bin/env python3
"""Strict offline rejection/protection review of the terminal batch04 parser failure."""
import argparse
import csv
import json
from pathlib import Path

import lzc_selector_native_product_batch_v4 as v4
from lzc_selector_native_prepare import require, sha, write

HERE = Path(__file__).resolve().parent


def diagnose(batch, output):
    require(batch.parent == output.parent == v4.batch.product.OUT and not output.exists(),
            'Fresh independent offline review directory required')
    plan = v4.reviewed_plan(batch)
    status = json.loads((batch / 'batch-status.json').read_bytes())
    launch = json.loads((batch / 'launch.json').read_bytes())
    require(status['status'] == 'FAILED_RECORDED_NOT_QUALIFICATION' and status['returncode'] == 0 and
            status['actual_script_sha256'] == launch['actual_script_sha256'] == sha(v4.SCRIPT) and
            launch['command'] == plan['command'], 'Exact actual script/terminal failure required')
    gui = (batch / 'DVEfiles/dve_gui.log').read_text()
    history = (batch / 'DVEfiles/dve_history.log').read_text()
    require('extra characters after close-brace' in gui and
            '(compiling body of proc "lpn_guard_exclude", line 3)' in gui and
            'return [gui_exclude_items {*}$args]' in gui and
            'LZC_NATIVE_BATCH_FAILED' in gui and
            gui.count('LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE') == 1 and
            gui.count('LZC_NATIVE_BATCH_V4_BUILTIN_PRESERVING_SESSION_LOADED') == 1 and
            'LZC_NATIVE_BATCH_SINGLETON_COMPLETE' not in gui,
            'Failure stack/boundary differs; cannot reuse diagnosis')
    rows = plan['protection_rows']
    checks = {}
    states = {}
    for stage in ('global-before', 'global-final'):
        path = batch / (stage + '.tsv')
        checks[stage] = v4.batch.audit(path, rows, -1)
        with path.open() as stream:
            states[stage] = list(csv.DictReader(stream, delimiter='\t'))
    changes = [dict(before=a, after=b) for a, b in zip(states['global-before'], states['global-final']) if a != b]
    require(not changes and (batch / 'global-before.tsv').read_bytes() ==
            (batch / 'global-final.tsv').read_bytes(), 'Protected state changed')
    require(sorted(p.name for p in batch.glob('case-*')) == ['case-000'], 'Unexpected later cases')
    case = batch / 'case-000'
    require({p.name for p in case.iterdir()} == {'before.tsv', 'initial-empty.el'}, 'Case advanced after guard failure')
    checks['case-000-before'] = v4.batch.audit(case / 'before.tsv', rows, -1, plan['targets'][0]['candidate']['scope'])
    for name in ('initial-empty.el', 'final-empty.el', 'case-000/initial-empty.el'):
        require((batch / name).read_bytes() == b'', 'Saved native exclusion not empty')
    require('gui_exclude_items ' not in history, 'Unexpected native exclusion history command')
    rejection = None
    try:
        v4.verify(batch, plan)
    except ValueError as error:
        rejection = str(error)
    require(rejection == 'Batch not completed/reset' and not (batch / 'batch-result.json').exists(),
            'Frozen verifier unexpectedly qualified incomplete batch')
    previous = json.loads((Path(plan['builtin_preserving_successor']['previous']) / 'batch-plan.json').read_bytes())
    require(plan['targets'] == previous['targets'] and rows == previous['protection_rows'], 'Input population drift')
    paths = [batch / 'batch-plan.json', batch / 'batch-plan.sha256.json', batch / 'batch-status.json',
             batch / 'launch.json', batch / 'DVEfiles/dve_gui.log', batch / 'DVEfiles/dve_history.log',
             batch / 'global-before.tsv', batch / 'global-final.tsv', batch / 'initial-empty.el',
             batch / 'final-empty.el', case / 'before.tsv', case / 'initial-empty.el',
             v4.SCRIPT, Path(v4.__file__), Path(__file__).resolve(),
             HERE / 'lzc_selector_native_product_guard_legacy.tcl',
             HERE / 'test_lzc_selector_native_product_guard_legacy.py']
    report = dict(status='INDEPENDENT_TERMINAL_REJECTION_PROTECTION_VERIFIED_NOT_QUALIFICATION',
        batch=str(batch), elapsed_seconds=status['elapsed_seconds'], returncode=status['returncode'],
        frozen_verifier_rejection=rejection, input_pins_verified=len(plan['pins']),
        audit_rows=checks, protected_state_differences=changes, all_saved_native_EL_empty=True,
        targets=120, target_differences=[], protected_positions=4200, input_protection_differences=[],
        completed_singletons=0, native_signature_qualified_candidates=0, actual_processor_waivers_added=0,
        observed_stack='DVE compile of lpn_guard_exclude line3 rejects return [gui_exclude_items {*}$args] before native call.',
        falsifiable_hypothesis='Embedded DVE parser rejects expansion syntax accepted by host Tcl. Runtime patchlevel not measured; do not infer exact version. Closed-gate invocation of original guard before load should reproduce the parse error, whereas fixed-arity guard should return only the intentional closed-gate rejection.',
        alternatives='Wrong native IDs/expressions, license failure and protected-state mismatch do not explain this compile stack. Global4200 and local84 audits passed; no native exclusion history entry or saved singleton exists.',
        candidate_repair=str(HERE / 'lzc_selector_native_product_guard_legacy.tcl'),
        repair_scope='Candidate guard uses eval of linsert-generated Tcl list; native builtin unchanged, no argument expansion. Host injection tests only, not DVE-qualified.',
        future_preflight='At reviewed successor entry before gui_open_cov/global audit: closed gate, print info patchlevel, call lpng_preflight. It must compile the guard and receive the exact intentional gate rejection, with no native/GUI call. Keep all target/protection/EL/reload/reset contracts unchanged.',
        no_new_session=True, application_approval=False, op16='HOLD', raw715_qualification=False,
        pins={str(p): sha(p) for p in paths})
    output.mkdir()
    write(output / 'terminal-review.json', report)
    write(output / 'terminal-review.sha256.json', {str(output / 'terminal-review.json'): sha(output / 'terminal-review.json')})
    print(json.dumps({k: report[k] for k in ('status', 'audit_rows', 'protected_state_differences', 'native_signature_qualified_candidates')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    diagnose(args.batch.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
