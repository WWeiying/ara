#!/usr/bin/env python3
"""Append explicitly audited current-image cases to the immutable 704-PASS ledger."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess
import time

from audit_probe_semantics_20261015 import ROOT, read, require, save, sha
from run_vcs_dve_batch import valid_vdb

BASE = ROOT / 'verification/out/full-regression-reviewed-20261015-01'
BUILD = ROOT / 'verification/out/full-regression-build-20261015-01'


def bound_execution_plan(index, detail, bound):
    original = ROOT / f'verification/out/full-regression-20261015-01/extensions/e{index:04d}/plan.json'
    path = Path(detail.get('execution_plan', original)).resolve()
    require(bound.get(str(original)) == sha(original), 'Original current case identity not bound')
    if path != original:
        require(index == 650 and detail.get('supersedes_plan') == str(original),
                'Only reviewed missing-vector-trace650 may replace its execution')
        old, new = read(original), read(path)
        require(new['index'] == index and new['elf_sha256'] == old['elf_sha256'] and
                new['command'][0] == old['command'][0] and new['work'] != old['work'],
                'Focused successor changed case, program or image')
        def normalized(command, vector):
            result, cursor = [], 0
            while cursor < len(command):
                arg = command[cursor]
                if arg in ('-l', '-cm_dir'):
                    result.extend((arg, '<new-output>')); cursor += 2
                elif arg == '-do':
                    script = command[cursor+1]
                    require(bound.get(script) == sha(script), 'Focused Tcl observer not authenticated')
                    result.extend((arg, sha(script))); cursor += 2
                elif arg.startswith(('+PRELOAD=', '+COMMIT_TRACE=')):
                    result.append(arg.split('=', 1)[0]+'=<same-input-or-new-output>'); cursor += 1
                elif arg.startswith('+VECTOR_TRACE='):
                    require(vector, 'Original650 unexpectedly had vector trace')
                    cursor += 1
                else:
                    result.append(arg); cursor += 1
            return result
        require(sum(c.startswith('+VECTOR_TRACE=') for c in new['command']) == 1 and
                normalized(old['command'], False) == normalized(new['command'], True),
                'Focused successor changed more than output locations and vector trace')
        require(new['vdb'] == str(Path(new['work']) / 'code.vdb'), 'Successor VDB not private work output')
    require(bound.get(str(path)) == sha(path), 'Actual current plan not bound')
    return path, read(path)


def overlay(original, summaries):
    rows = {r['index']: copy.deepcopy(r) for r in original['cases']}
    require(len(rows) == len(original['cases']) == 798 and set(rows) == set(range(798)), 'Exact original798 selection required')
    pending = {i for i, row in rows.items() if row['status'] == 'CHECKER_REQUIRED'}
    require(len(pending) == 94 and sum(r['status'] == 'PASS' for r in rows.values()) == 704, 'Expected immutable704+94 baseline')
    seen, pins = set(), {}
    for path in summaries:
        path = Path(path).resolve()
        pins[str(path)] = sha(path)
        for record in read(path)['cases']:
            index = record['index']
            require(type(index) is int and index in pending and index not in seen, 'Unrequested or duplicate audit index')
            seen.add(index)
            detail_path = Path(record['report']).resolve()
            detail = read(detail_path)
            pins[str(detail_path)] = sha(detail_path)
            require(detail['index'] == index and detail['status'] == record['status'], 'Summary/detail verdict disagreement')
            status = detail['status']
            require(status in ('PASS', 'FAIL', 'CHECKER_REQUIRED'), 'Unsupported audit status')
            if status == 'PASS':
                bound = detail.get('input_pins', {})
                require(isinstance(bound, dict) and len(bound) >= 4, 'PASS lacks authenticated evidence inputs')
                plan_path, plan = bound_execution_plan(index, detail, bound)
                receipt_path = plan_path.parent / 'simulation-exit.json'
                require(bound.get(str(receipt_path)) == sha(receipt_path), 'Actual OS wait not bound')
                receipt = read(receipt_path)
                require(receipt['executed'] is True and type(receipt['returncode']) is int and
                        receipt['returncode'] == 0 and receipt['timed_out'] is False and
                        receipt['cancelled'] is False and receipt['command'] == plan['command'] and
                        receipt['cwd'] == plan['work'], 'Actual current execution not successful')
                image_book = read(BUILD / 'build-image.json')
                image = str(BUILD / 'sim/simv')
                require(plan['command'][0] == image and bound.get(image) == image_book[image] == sha(image),
                        'Current image identity is not authenticated')
                elf = plan_path.parent / 'input.elf'
                require(bound.get(str(elf)) == plan['elf_sha256'] == sha(elf), 'Current ELF identity not bound')
                for name in ('commit_trace.csv', 'vector_trace.csv'):
                    trace = Path(plan['work']) / name
                    require(bound.get(str(trace)) == sha(trace), 'Actual trace absent from PASS evidence')
                for name, digest in bound.items():
                    require(sha(name) == digest, 'Audit evidence changed: ' + name)
                require(detail.get('old_PASS_reused', False) is False, 'Historical PASS is not a current oracle')
                if detail.get('execution_plan'):
                    rows[index]['vdb'] = plan['vdb']
            rows[index].update(status=status, reason=detail.get('reason'),
                               evidence=rows[index]['evidence'] + [str(detail_path)],
                               acceptance='current-image specialized semantic audit' if status == 'PASS' else None)
    require(seen == pending, 'Missing pending-case audits: ' + str(sorted(pending - seen)))
    return [rows[i] for i in range(798)], pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--wait-for-audits', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state = dict(status='AUDITING')
    save(output / 'status.json', state)
    try:
        deadline = time.monotonic() + 1800
        while any(not path.is_file() for path in args.audit):
            require(args.wait_for_audits and time.monotonic() < deadline, 'Required audit summary not complete')
            state.update(status='WAITING_FOR_AUDITS', missing_audits=[str(p) for p in args.audit if not p.is_file()])
            save(output / 'status.json', state)
            time.sleep(15)
        state.pop('missing_audits', None)
        state['status'] = 'AUDITING'
        save(output / 'status.json', state)
        rows, pins = overlay(read(BASE / 'case-ledger.json'), args.audit)
        counts = dict(Counter(r['status'] for r in rows))
        plan = read(ROOT / 'verification/out/full-regression-20261015-01/full-regression-core-20261015-01/plan.json')
        for path, digest in plan['image'].items():
            require(sha(path) == digest, 'Current simulator image changed')
        databases = [plan['design_vdb']]
        for row in rows:
            if row['status'] == 'PASS':
                valid_vdb(Path(row['vdb']), row['coverage_test'], plan['simv'])
                databases.append(row['vdb'])
        require(len(set(databases)) == len(databases), 'Duplicate admitted VDB')
        save(output / 'case-ledger.json', dict(total=798, counts=counts, cases=rows,
             original_ledger=str(BASE / 'case-ledger.json'), audit_pins=pins,
             old_evidence_modified=False, failed_and_unreviewed_excluded=True))
        inputs = output / 'pass-vdbs.txt'
        inputs.write_text('\n'.join(databases) + '\n')
        state.update(status='FUNCTIONALLY_AUDITED', total=798, counts=counts,
                     passed=counts.get('PASS', 0), excluded=798-counts.get('PASS', 0))
        save(output / 'status.json', state)
        if args.collect:
            state['status'] = 'DVE_RUNNING'
            save(output / 'status.json', state)
            command = ['bash', str(ROOT / 'verification/coverage/dve_hierarchy/run_dve_coverage.sh'),
                       str(output / 'dve'), '--inputs-file', str(inputs)]
            save(output / 'dve.command.json', dict(command=command))
            with (output / 'dve.log').open('x') as stream:
                result = subprocess.run(command, cwd=ROOT, env=dict(os.environ,
                    DVE_COVERAGE_TIMEOUT='1800', DVE_WAIVERS='auto'),
                    stdout=stream, stderr=subprocess.STDOUT, timeout=1920)
            require(result.returncode == 0 and (output / 'dve/summary.csv').is_file(), 'DVE report failed')
            state['status'] = 'COMPLETE' if counts.get('PASS') == 798 else 'COMPLETE_WITH_NONPASS'
        save(output / 'status.json', state)
        print(json.dumps(state), flush=True)
    except Exception as error:
        state.update(status='STOPPED', reason=f'{type(error).__name__}: {error}')
        save(output / 'status.json', state)
        raise


if __name__ == '__main__':
    main()
