#!/usr/bin/env python3
"""Fresh repaired-image MVP gate, 600-case replay and PASS-only DVE export."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import build_memory_vl0_repair as builder
import run_full_recollection_20260928 as campaign

base = builder.base
ROOT = base.ROOT
MAIN = Path('/home/wangwy/openproject/ara_dsa')
MVP_RUNNER = ROOT / 'verification/fpu/run_mvp_repair.py'
MVP_PASS = ROOT / 'verification/out/mvp-repair-20260930-03/summary.json'
MVP_INPUTS = MVP_PASS.parent / 'inputs.json'
WALL_EVIDENCE = ROOT / ('verification/out/main-aligned-vfdiv-retry-20260930-01/results/'
                        'c0597-vfdiv_mask_flags-4805d7ca8b6f/work/run.vcs.log')


def alignment():
    records = {}
    for directory in ('hardware/src', 'hardware/include', 'hardware/deps/fpu_div_sqrt_mvp/hdl'):
        left = {str(p.relative_to(MAIN)): base.sha256(p)
                for p in (MAIN / directory).rglob('*') if p.is_file()}
        right = {str(p.relative_to(ROOT)): base.sha256(p)
                 for p in (ROOT / directory).rglob('*') if p.is_file()}
        if left != right:
            raise RuntimeError('Main/verification mismatch: ' + directory)
        records.update({str(MAIN / p): digest for p, digest in left.items()})
        records.update({str(ROOT / p): digest for p, digest in right.items()})
    for path in ('hardware/src/lane/vmfpu.sv', 'hardware/deps/cva6/core/fpu_wrap.sv'):
        if 'fpnew_pkg::THMULTI' not in (ROOT / path).read_text():
            raise RuntimeError('Active divider configuration changed')
    result = base.read(MVP_PASS)
    if result.get('status') != 'PASS' or result.get('completed_cases') != 178 or result.get('failures'):
        raise RuntimeError('Missing focused MVP repair evidence')
    for relative, digest in base.read(MVP_INPUTS).items():
        base.check({str(MAIN / 'hardware/deps' / relative): digest,
                    str(ROOT / 'hardware/deps' / relative): digest})
    return records


def reviewed_inventory(selection):
    selected = original_inventory(selection)
    found = [case for case in selected['cases'] if case.get('coverage_test') == 'vfdiv_mask_flags']
    if len(found) != 1 or found[0]['kind'] != 'uvm':
        raise RuntimeError('Ambiguous reviewed long DIV gate')
    if not WALL_EVIDENCE.is_file() or 'PASSED' not in WALL_EVIDENCE.read_text(errors='replace'):
        raise RuntimeError('Missing completed long DIV evidence')
    case = found[0]
    case['wall_timeout_adjustment'] = {'previous_seconds': case['timeout_s'],
        'reviewed_seconds': 1200, 'evidence': str(WALL_EVIDENCE),
        'reason': 'same-ELF prior run completed after the 600-second wall budget; no RTL watchdog change'}
    case['timeout_s'] = max(case['timeout_s'], 1200)
    selected['case_bounds'] = campaign.validate_bounds(selected['cases'], selected['gate_cases'])
    selected['files'].update(base.pins([WALL_EVIDENCE]))
    return selected


original_inventory = campaign.inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    build = base.checked_output(args.build_output)
    output = base.checked_output(args.output)
    if build.exists() or output.exists():
        raise RuntimeError('New independent output directories required')
    approved = alignment()
    selected = reviewed_inventory(campaign.DEFAULT_PLAN)
    campaign.tool_paths()
    if args.preflight:
        print(json.dumps({'status': 'READY', 'cases': len(selected['cases']),
                          'gate_cases': len(selected['gate_cases']), 'workers': 8,
                          'mvp_cases': 178, 'historical_vdb_reuse': False}, indent=2))
        return 0
    base.check_service()
    if os.environ.get('ARA_CHECKPOINT_UNIT') != 'ara-full-recollection-' + output.name + '.service':
        raise RuntimeError('Service/campaign identity mismatch')
    os.environ['PYTHONPATH'] = str(ROOT / 'verification')
    build.mkdir()
    state = {'status': 'MVP_GATE', 'campaign': str(output), 'workers': 8,
             'active_divider': 'THMULTI', 'historical_vdb_reuse': False}
    status = build / 'pipeline-status.json'
    base.save(status, state)
    base.save(build / 'approved-source-pins.json', approved)
    try:
        focused = build / 'mvp-regression'
        with (build / 'mvp-regression.log').open('w') as stream:
            subprocess.run([sys.executable, str(MVP_RUNNER), '--output', str(focused)],
                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        base.check(approved)
        state.update(status='BUILDING', mvp_qualification='178_BOUNDED_CASES_PASS')
        base.save(status, state)
        sys.argv = [builder.__file__, '--output', str(build),
                    '--approved-dispatcher-sha256', base.sha256(builder.DISPATCHER)]
        builder.main()
        base.check(approved)
        result = base.read(build / 'build-status.json')
        if result['status'] != 'PASS':
            raise RuntimeError('New image failed source/configuration audit')
        evidence = focused / 'summary.json'
        files = dict(approved, **base.pins([Path(__file__), MVP_RUNNER, MVP_PASS, MVP_INPUTS,
                     evidence, focused / 'inputs.json', build / 'build-status.json']))
        freeze = build / 'recollection-freeze.json'
        base.save(freeze, {'status': 'READY_FOR_FULL_RECOLLECTION',
            'simv': str(build / 'sim/simv'), 'image': result['image'], 'files': files,
            'repair_evidence': [str(evidence)],
            'qualification_scope': 'THMULTI full collection; MVP bounded standalone gate only'})
        campaign.inventory = reviewed_inventory
        campaign.prepare(output, campaign.DEFAULT_PLAN, freeze)
        state.update(status='GATED_RECOLLECTION_STARTED', freeze=str(freeze))
        base.save(status, state)
        os.execv(sys.executable, [sys.executable, campaign.__file__, '--output', str(output), '--execute'])
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        base.save(status, state)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
