#!/usr/bin/env python3
"""Authenticate RED32 gold by the parent's pinned independent software replay.

Publish one replacement case and a final disjoint 35-case summary. The frozen
architecture auditor, its other 34 results, and all raw reports stay unchanged.
"""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path[:0] = [str(Path(__file__).resolve().parent)]
import audit_pending_fpu_20261016 as base
from audit_probe_semantics_20261015 import read, require, save, sha, install_guard

ROOT = base.ROOT
REFERENCE = ROOT / 'verification/out/pending94-red32-reference-20261016-01/audit.json'
REFERENCE_SHA = 'c8bd2a23a1f1f301c46db7c14ad518008f9ba361430ab6e9b1063cd2c7dd4c5e'
REPRODUCER = ROOT / 'verification/coverage/reproduce_red32_reference_20261016.py'
REPRODUCER_SHA = 'ef596b738611f195790206d08aa87e971ed47cce13c329c5e0a3bae0fe4e6a13'
SPIKE_SHA = 'c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2'


def validate_receipt(record, receipt, command, elf_sha):
    require(record['status'] == 'PASS' and record['exact_all_parsed_commit_fields'] is True
            and record['historical_PASS_reused'] is False and record['RTL_simulation_started'] is False,
            'Independent exact software reproduction required')
    require(receipt == record['receipt'] and receipt['command'] == command
            and type(receipt['returncode']) is int and receipt['returncode'] == 0
            and receipt['finished'] > receipt['started'], 'Successful actual software wait identity required')
    require(command[1:-1] == ['--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits'],
            'Original independent Spike options required')
    require(receipt['input_pins'] == record['input_pins']
            and record['input_pins'][command[0]] == SPIKE_SHA
            and record['input_pins'][command[-1]] == elf_sha,
            'Source-book-pinned Spike and identical ELF required')


def authenticate(a):
    a.bind(__file__)
    a.bind(ROOT / 'verification/tests/test_audit_pending_fpu_red32_reference_20261016.py')
    record = a.bind_json(REFERENCE, REFERENCE_SHA)
    a.bind(REPRODUCER, REPRODUCER_SHA)
    receipt = a.bind_json(REFERENCE.parent / 'execution.json')
    original_elf = Path(next(c.split('=', 1)[1] for c in a.plan['original_command'] if c.startswith('+PRELOAD=')))
    command = a.bind_json(original_elf.parent / 'spike.command.json')['command']
    require(command[-1] == str(original_elf) and receipt['cwd'] == str(REFERENCE.parent), 'Original software execution paths differ')
    validate_receipt(record, receipt, command, a.plan['elf_sha256'])
    for path, digest in record['input_pins'].items():
        a.bind(path, digest)
    book_path = original_elf.parents[2] / 'source-pins.json'
    book = a.bind_json(book_path, record['input_pins'][str(book_path)])
    require(all(book[path] == record['input_pins'][path] for path in (command[0], command[-1])),
            'Independent software binary/ELF authority differs from original source book')
    original_trace = original_elf.parent / 'spike.trace'
    reproduced = REFERENCE.parent / 'spike.trace'
    require(record['original_trace'] == str(original_trace) and record['reproduced_trace'] == str(reproduced),
            'Exact original/reproduced reference paths required')
    a.bind(original_trace, record['original_trace_sha256'])
    a.bind(reproduced, record['reproduced_trace_sha256'])
    from ara_verify.spike_trace import parse_spike_commits
    original = parse_spike_commits(original_trace)
    regenerated = parse_spike_commits(reproduced)
    require(len(original) == len(regenerated) == record['commits'] == 20000,
            'Complete independently reproduced reference population required')
    require(all(a == b for a, b in zip(original, regenerated)), 'Canonical independent software reference differs')
    proof = dict(status='PASS', authority=str(REFERENCE), authority_sha256=REFERENCE_SHA,
        original_trace=str(original_trace), original_trace_sha256=record['original_trace_sha256'],
        reproduced_trace=str(reproduced), reproduced_trace_sha256=record['reproduced_trace_sha256'],
        commits=20000, all_parsed_commit_fields_equal=True, receipt=str(REFERENCE.parent / 'execution.json'),
        source_book=str(book_path), Spike_sha256=SPIKE_SHA, identical_ELF_sha256=a.plan['elf_sha256'],
        historical_PASS_reused=False, fresh_hash_alone_used_as_gold_authority=False,
        software_reference_runs_by_parent=1, RTL_simulation_runs=0)
    save(a.out / 'red32-reference-authentication.json', proof)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-audit', type=Path, default=ROOT / 'verification/out/pending-fpu-audit-20261016-03/audit.json')
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'verification/out') and not output.exists(), 'Fresh independent final output required')
    old = read(args.base_audit)
    require({r['index'] for r in old['cases']} == set(base.CASES) and len(old['cases']) == 35,
            'Complete frozen 35-case architecture/waveform audit required')
    install_guard(output)
    output.mkdir()
    old_exact = base.red32_exact
    def authenticated_exact(a, *rest):
        authenticate(a)
        return old_exact(a, *rest)
    base.red32_exact = authenticated_exact
    replacement = base.audit_one(660, output)
    rows, pins = [], {str(args.base_audit.resolve()): sha(args.base_audit), str(Path(__file__).resolve()): sha(__file__)}
    for row in old['cases']:
        if row['index'] == 660:
            rows.append(replacement)
            continue
        report = Path(row['report'])
        require(report.is_absolute() and report.is_relative_to(ROOT / 'verification/out'), 'Absolute owned case report required')
        case = read(report)
        require(case['index'] == row['index'] and case['status'] == row['status'], 'Frozen case summary/report disagreement')
        if case['status'] == 'PASS':
            require(case['execution_identity'] is not None and case['semantic']['status'] == 'PASS',
                    'Actual execution and original architecture acceptance required')
            if row['index'] in base.RESET_CASES:
                require(case['semantic']['microstructure_witness']['status'] == 'PASS', 'Mandatory reset waveform must pass')
        pins[str(report)] = sha(report)
        rows.append(row)
    save(output / 'summary-input-pins.json', pins)
    result = dict(cases=rows, accepted=[r['index'] for r in rows if r['status'] == 'PASS'],
        rejected=[r['index'] for r in rows if r['status'] == 'FAIL'],
        checker_required=[r['index'] for r in rows if r['status'] == 'CHECKER_REQUIRED'],
        summary_input_pins=pins, replacement_case=660, independently_regenerated_gold=str(REFERENCE),
        preserved_predecessor_audit=str(args.base_audit.resolve()), RTL_simulation_runs=0, coverage_admitted=False)
    save(output / 'audit.json', result)
    print('Final', len(result['accepted']), 'PASS;', result['rejected'], 'FAIL;', result['checker_required'], 'CHECKER_REQUIRED', flush=True)


if __name__ == '__main__':
    main()
