#!/usr/bin/env python3
"""Close a measured host-time VFDiv truncation, then resume the frozen suite."""
import json
from pathlib import Path
import re

import run_full_recollection_20260928 as full
import retry_vfdiv_wall_budget as retry
import consolidate_vfdiv_gate as consolidation
import resume_full_recollection_20260929 as resume
from finish_main_alignment_20260930 import task_cycles

ROOT = full.ROOT
SOURCE = ROOT / 'verification/out/main-aligned-600-20260930-01'
RETRY = ROOT / 'verification/out/main-aligned-vfdiv-retry-20260930-01'
OLD = ROOT / 'verification/out/full-recollection-20260928-02'
BUILD = ROOT / 'verification/out/main-aligned-build-20260930-01'
SERVICE = 'ara-main-aligned-gate-resume-20260930-01.service'
NAME = 'c0597-vfdiv_mask_flags-4805d7ca8b6f'


def evidence():
    relative = Path('results') / NAME / 'work/console.log'
    old = (OLD / relative).read_text()
    new = (SOURCE / relative).read_text()
    events = r'^\[ARA_CONTRACT_TRACE\].*$'
    before, after = re.findall(events, old, re.M), re.findall(events, new, re.M)
    complete = r'^CASE id=\d+[^\n]*expected=[^\n]*'
    before_cases, after_cases = re.findall(complete, old, re.M), re.findall(complete, new, re.M)
    if len(after) < 400 or before[:len(after)] != after:
        raise RuntimeError('Event/cycle prefix mismatch; do not retry as a budget failure')
    if len(after_cases) < 30 or before_cases[:len(after_cases)] != after_cases:
        raise RuntimeError('Result/flag prefix mismatch')
    for path in (OLD, SOURCE):
        item = full.read(path / 'outcomes' / (NAME + '.json'))
        full.require(item['elf_sha256'] == full.read(OLD / 'outcomes' / (NAME + '.json'))['elf_sha256'],
                     'Stimulus mismatch')
    full.save(BUILD / 'vfdiv-budget-evidence.json', {
        'events_identical_including_cycles': len(after),
        'completed_cases_identical': len(after_cases),
        'last_complete_case': after_cases[-1],
        'change': 'single host wall timeout 600 -> 1200; no RTL/ELF/watchdog/checker change'})


def comparison():
    rows = []
    for path in sorted((SOURCE / 'outcomes').glob('*.json')):
        prior = OLD / 'outcomes' / path.name
        if not prior.is_file():
            continue
        old, new = full.read(prior), full.read(path)
        full.require(old['elf_sha256'] == new['elf_sha256'], 'ELF mismatch')
        before = task_cycles(OLD / 'results' / new['name'])
        after = task_cycles(SOURCE / 'results' / new['name'])
        comparable = old['status'] == new['status'] == 'PASS' and before and after
        rows.append({'name': new['name'], 'old_status': old['status'], 'new_status': new['status'],
                     'old_cycles': before, 'new_cycles': after,
                     'ratio': after / before if comparable else None})
    full.save(BUILD / 'evaluation-resumed.json', {
        'campaign': full.read(SOURCE / 'checkpoint.json'),
        'cycle_comparisons': rows,
        'mvp_qualification': 'FAIL; not used by the active THMULTI configuration'})


def main():
    full.base.check_service()
    evidence()
    original_frozen = full.frozen
    if retry.run(SOURCE, RETRY):
        return 1
    # The isolated retry temporarily installs a single-case plan validator.
    full.frozen = original_frozen
    consolidation.consolidate(SOURCE, RETRY)
    resume.SERVICE = SERVICE
    resume.prepare(SOURCE)
    rc = resume.execute(SOURCE)
    comparison()
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
