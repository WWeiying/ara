"""Reconcile all matrix nonpasses; issue routing is not causal proof."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


INVENTORIES = (
    ('original', 'rvv_inventory105'),
    ('fp_move_extension_children', 'rvv_partition_inventory57'),
    ('permutation_children', 'rvv_permute_partition_inventory69'),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row):
    return row['scope'], row['name'], row['sha256']


def issue_routes(name, status):
    if status == 'mixed_outcomes':
        return ['observation_gap_not_established_rtl_failure']
    if status == 'not_attempted':
        return ['unexecuted_not_a_failure']
    if name.startswith('rvv_extension_'):
        return ['RVV-06']
    if name.startswith('rvv_exceptions'):
        return ['RVV-04']
    if name.startswith('rvv_whole_registers'):
        return ['RVV-03']
    if name.startswith('rvv_reduction_fpwide'):
        return ['RVV-05']
    if name.startswith('rvv_fp_redspecial'):
        return ['RVV-07']
    if name.startswith('rvv_segments_misaligned'):
        return ['CAP-01']
    if name.startswith('rvv_segment_alignment'):
        return ['RVV-18']
    if name.startswith('rvv_fault_replay'):
        if '_indexed_' in name:
            return ['RVV-15']
        if status == 'stalled' and 'zero_stride' in name:
            return ['RVV-16']
        return ['masked_memory_fault_candidate_not_all_replay_errors']
    if name.startswith('rvv_fp_compare'):
        return ['RVV-09', 'RVV-11'] if 'restart' in name else ['RVV-09', 'comparison_data_cause_open']
    if name.startswith('rvv_fp_move_restart'):
        return ['RVV-10', 'slide_stall_candidate']
    if name.startswith('rvv_masks_scalar_restart'):
        return ['RVV-12']
    if name.startswith('rvv_masks_cmp_alias_restart'):
        return ['RVV-13']
    if name.startswith('rvv_masks_alias_restart'):
        return ['RVV-17']
    if name.startswith(('rvv_fixed_', 'rvv_integer_macc_')):
        return ['RVV-02']
    if name.startswith('rvv_permute_restart'):
        return ['RVV-14', 'RVV-19', 'RVV-20', 'RVV-21']
    if name.startswith('rvv_permute_'):
        return ['RVV-08']
    return ['UNMAPPED']


def audit(base):
    rows, sources, checks = [], {}, {}
    for scope, folder in INVENTORIES:
        path = base / folder / 'inventory.json'
        inventory = json.loads(path.read_text())
        sources[str(path)] = digest(path)
        for filename, expected in inventory['source_sha256'].items():
            if filename not in checks:
                p = Path(filename)
                checks[filename] = digest(p) if p.is_file() else None
            if checks[filename] != expected:
                raise ValueError('Changed/missing inventory evidence: ' + filename)
        for case in inventory['cases']:
            if case['status'] != 'passed':
                rows.append(dict(scope=scope, **case))
    ledger_path = base / 'rvv_failure_retest01/results.json'
    ledger = json.loads(ledger_path.read_text())
    sources[str(ledger_path)] = digest(ledger_path)
    retests = {identity(r): r for r in ledger['cases']}
    expected = {identity(r) for r in rows if r['status'] != 'not_attempted'}
    if len(retests) != len(ledger['cases']) or expected != set(retests):
        raise ValueError('Retest ledger identity mismatch or duplicate')
    report_counts = Counter()
    for row in rows:
        retest = retests.get(identity(row), {})
        row['retest_status'] = retest.get('retest_status', 'not_in_retest_ledger')
        row['issue_routes_not_proven_causes'] = issue_routes(row['name'], row['status'])
        row['internal_cause_proven_by_this_audit'] = False
        row['retest_reports'] = sorted({a['report'] for a in retest.get('retest_attempts', [])})
        row['family'] = re.sub(r'_e\d+.*', '', row['name'])
        report_counts[row['status']] += 1
    supplemental = []
    for name in ('campaign03_triage_08.json', 'width_fault_timeout02.json',
                 'width_restart04_live.json', 'rvv_extended04/report.json',
                 'rvv_extended04/m8_report.json', 'rvv_extended04/resume02_report.json',
                 'rvv_extended04/resume03_report.json'):
        path = base / name
        data = json.loads(path.read_text())
        sources[str(path)] = digest(path)
        records = data.get('failures', data.get('results', []))
        supplemental.append(dict(source=str(path), source_sha256=sources[str(path)],
            nonpass_records=[r for r in records if r.get('status') != 'passed'],
            limitation='Historical snapshot; running is not independently a confirmed stall'))
    issues = Path(__file__).resolve().parent.parent / 'ISSUES.md'
    sources[str(issues)] = digest(issues)
    headings = re.findall(r'^## (.+)$', issues.read_text(), re.M)
    return dict(scope='Three pinned matrix inventories plus explicitly named early evidence; not all campaigns',
        sources=sources, verified_inventory_sources=len(checks),
        counts=dict(report_counts), total_nonpass_or_unexecuted=len(rows),
        ledger_identity_reconciliation=True, ledger_cases=len(retests),
        retest_counts=dict(Counter(r['retest_status'] for r in rows if identity(r) in retests)),
        unmapped=[r['name'] for r in rows if 'UNMAPPED' in r['issue_routes_not_proven_causes']],
        issue_register=headings, cases=rows, supplemental=supplemental,
        root_cause_audit_complete=False, rtl_modified=False,
        limitations=['Parent and child ELF records are not additive independent defects',
                    'A family route does not verify a shared cause or close a failure',
                    'A failed instruction before a stall does not identify the stalled trial',
                    'A passed reduction or retest does not erase a historical failure'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.campaign)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('counts', 'ledger_cases', 'retest_counts',
        'verified_inventory_sources', 'unmapped', 'root_cause_audit_complete')}, indent=2))


if __name__ == '__main__':
    main()
