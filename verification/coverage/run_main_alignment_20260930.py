#!/usr/bin/env python3
"""Rebuild aligned product RTL and replay the existing 600-case gated suite.

MVP is a failed, quarantined alternative divider. This campaign qualifies only
the explicitly selected THMULTI configuration; it cannot qualify MVP.
"""
import argparse
import os
from pathlib import Path
import sys

import build_memory_vl0_repair as builder
import run_full_recollection_20260928 as campaign

base = builder.base
MAIN = Path('/home/wangwy/openproject/ara_dsa')
ALIGNMENT = base.ROOT / 'verification/out/main-alignment-20260930-01'
MVP = base.ROOT / 'verification/out/main-mvp-evaluation-20260930-01/summary.json'


def aligned():
    records = base.read(ALIGNMENT / 'alignment.before.json')
    for record in records:
        path = record['path']
        expected = record['main_sha256']
        base.check({str(MAIN / path): expected, str(base.ROOT / path): expected})
    for directory in ('hardware/src', 'hardware/include'):
        left = {p.relative_to(MAIN): base.sha256(p)
                for p in (MAIN / directory).rglob('*') if p.is_file()}
        right = {p.relative_to(base.ROOT): base.sha256(p)
                 for p in (base.ROOT / directory).rglob('*') if p.is_file()}
        if left != right:
            raise RuntimeError('Product/verification RTL drift: ' + directory)
    for path in ('hardware/src/lane/vmfpu.sv', 'hardware/deps/cva6/core/fpu_wrap.sv'):
        if 'fpnew_pkg::THMULTI' not in (base.ROOT / path).read_text():
            raise RuntimeError('Reviewed active divider configuration changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build = base.checked_output(args.build_output)
    output = base.checked_output(args.output)
    base.check_service()
    if os.environ['ARA_CHECKPOINT_UNIT'] != 'ara-full-recollection-' + output.name + '.service':
        raise RuntimeError('Service/campaign identity mismatch')
    if build.exists() or output.exists():
        raise RuntimeError('Independent new output directories required')
    aligned()
    mvp = base.read(MVP)
    if mvp['status'] != 'AUDIT_REPRODUCED_DUT_FAILURES' or mvp['errors']:
        raise RuntimeError('MVP diagnosis missing or unreliable')
    build.mkdir()
    state = {'status': 'BUILDING', 'campaign': str(output), 'workers': 8,
             'active_divider': 'THMULTI', 'mvp_qualification': 'FAIL_NOT_USED',
             'historical_vdb_reuse': False}
    status = build / 'pipeline-status.json'
    base.save(status, state)
    try:
        sys.argv = [builder.__file__, '--output', str(build),
                    '--approved-dispatcher-sha256', base.sha256(builder.DISPATCHER)]
        builder.main()
        aligned()
        result = base.read(build / 'build-status.json')
        if result['status'] != 'PASS':
            raise RuntimeError('New image failed source/configuration audit')
        files = base.pins([Path(__file__), ALIGNMENT / 'alignment.before.json',
                           MVP, build / 'build-status.json'])
        freeze = build / 'recollection-freeze.json'
        base.save(freeze, {'status': 'READY_FOR_FULL_RECOLLECTION',
                          'simv': str(build / 'sim/simv'), 'image': result['image'],
                          'files': files, 'repair_evidence': [str(MVP)],
                          'qualification_scope': 'THMULTI; MVP failed standalone audit'})
        campaign.prepare(output, campaign.DEFAULT_PLAN, freeze)
        state.update(status='GATED_RECOLLECTION_STARTED', freeze=str(freeze))
        base.save(status, state)
        os.execv(sys.executable, [sys.executable, campaign.__file__,
                                 '--output', str(output), '--execute'])
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        base.save(status, state)
        raise


if __name__ == '__main__':
    main()
