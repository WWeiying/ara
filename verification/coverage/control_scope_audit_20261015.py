#!/usr/bin/env python3
"""Audit scalar/CSR programs without pretending that they must allocate a VID.

This is a new, explicit acceptance scope over immutable simulator evidence. It
does not change old UVM diagnostics, disable protocol checks, or admit ordinary
vector programs with missing traffic.
"""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import replay_historical_extensions_20261015 as replay
from ara_verify.contract import parse_contract_summary
from ara_verify.runner import FAIL_RE, SUCCESS_RE
from ara_verify.trace import is_vector_instruction, validate_trace

PROFILES = {
    616: ('linux_csr_gap33', 1, 'linux_csr_gap33 checks=178 failures=0'),
    617: ('sv39_gap34_load', 0, 'sv39_gap34_load phases=21 checks=85 failures=0'),
    618: ('sv39_gap34_store', 0, 'sv39_gap34_store phases=21 checks=91 failures=0'),
    619: ('sv39_gap34_fetch', 0, 'sv39_gap34_fetch phases=21 checks=105 failures=0'),
    620: ('scalar_gap35_memory', 0, 'scalar_gap35_memory checks=301 failures=0'),
    621: ('scalar_gap35_alu_control', 0, 'scalar_gap35_alu_control checks=33 failures=0'),
    622: ('scalar_gap35_illegal', 0, 'scalar_gap35_illegal checks=190 failures=0'),
    623: ('csr_gap35_counteren', 0, 'csr_gap35_counteren phases=36 checks=392 illegal=16 legal=20 failures=0'),
    624: ('csr_gap35_fp_rw', 0, 'csr_gap35_fp_rw phases=75 checks=777 illegal=27 legal=48 failures=0'),
    629: ('csr_gap35_permissions', 0, 'csr_gap35_permissions phases=132 checks=1236 illegal=126 legal=6 failures=0'),
    638: ('fence_t_gap36_smoke', 0, 'fence_t_gap36_smoke rounds=2 checks=458 failures=0'),
    639: ('gap37_csr_alias_tvm', 0, 'gap37_csr_alias_tvm phases=52 checks=626 illegal=7 legal=45 failures=0'),
    641: ('csr_gap44_absent', 0, 'csr_gap44_absent phases=52 checks=1290 illegal=50 legal=2 failures=0'),
    647: ('sv39_gap52_superpage_sfence_pmp0', 42, 'gap35 checks=110 failures=0'),
    648: ('scalar_gap63_zcb_reject', 0, 'scalar_gap63_zcb_reject checks=82 failures=0'),
    651: ('sv39_gap68_warm_permissions_pmp0', 20, 'gap35 checks=71 failures=0'),
    727: ('fence_t_u_padding_successor', 0, 'fence_t_u_padding_successor legacy_checks=458 extra_checks=241 failures=0'),
}
ERROR_TEXT = {
    'CVXIF/NO_TRAFFIC': 'scoreboard observed no complete CVXIF traffic',
    'VID/NO_TRAFFIC': 'real Ara program did not allocate a backend vid',
}
CONTROL_CSRS = {0x008, 0x009, 0x00A, 0x00F, 0xC20, 0xC21, 0xC22}
require = replay.require


def control_instruction(insn):
    return (insn & 0x7f) == 0x73 and ((insn >> 12) & 7) != 0 and (insn >> 20) in CONTROL_CSRS


def audit_log(text, requests, marker):
    lines = text.splitlines()
    require(lines.count(marker) == 1, 'missing/duplicate exact firmware check count')
    require(sum(bool(SUCCESS_RE.search(line)) for line in lines) == 1, 'one actual Core SUCCESS required')
    errors = []
    expected_ids = ['VID/NO_TRAFFIC'] if requests else ['CVXIF/NO_TRAFFIC', 'VID/NO_TRAFFIC']
    for line in lines:
        if line.startswith('UVM_ERROR ') and not re.fullmatch(r'UVM_ERROR\s*:\s*\d+', line.strip()):
            m = re.fullmatch(r'UVM_ERROR \S*/ara_cvxif_uvm_pkg\.sv\(\d+\) @ \d+: '
                             r'\S+ \[([^\]]+)\] (.*)', line)
            require(m is not None and m[1] in expected_ids and m[2] == ERROR_TEXT[m[1]],
                    'unscoped UVM error: ' + line)
            errors.append(m[1])
            continue
        if re.fullmatch(r'UVM_ERROR\s*:\s*\d+', line.strip()):
            require(int(line.split(':')[-1]) == len(expected_ids), 'UVM error accounting differs')
            continue
        firmware_error = re.search(r'^\s*(?:FAIL|FAILED)(?:[:\s]|$)|\b(?:failures|errors|num_failed)=[1-9]\d*\b', line)
        require(not FAIL_RE.search(line) and not replay.RAW_FAIL.search(line) and not firmware_error,
                'runtime failure: ' + line)
    require(errors == expected_ids, 'scope diagnostic count/order differs')
    require(len(re.findall(r'^UVM_ERROR\s*:\s*\d+\s*$', text, re.M)) == 1,
            'missing/duplicate UVM severity summary')
    request_counts = re.findall(r'\[CVXIF/COUNT\] observed requests=(\d+) responses=(\d+) '
                                r'aborted=(\d+) reused=(\d+) immediate=(\d+)', text)
    require(request_counts == [(str(requests), str(requests), '0', '0', str(requests))],
            'CVXIF traffic is not the exact control-only transaction population')
    require(re.findall(r'\[VID/COUNT\] allocations=(\d+) completions=(\d+) aborted=(\d+) max_live=(\d+)', text)
            == [('0', '0', '0', '0')], 'unexpected backend traffic')
    summaries = [parse_contract_summary(line) for line in lines if '[ARA_CONTRACT]' in line]
    require(len(summaries) == 1 and summaries[0] is not None, 'one complete contract summary required')
    summary = summaries[0]
    require(summary['requests'] == summary['responses'] == requests, 'contract/trace population mismatch')
    require(all(summary[k] == 0 for k in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
            'protocol or payload stability violation')
    return dict(scope_diagnostics=errors, protocol=summary)


def audit_case(case, member):
    plan = replay.read(case / 'plan.json')
    index = plan['index']
    require(index in PROFILES, 'not a reviewed scalar/control case')
    name, requests, marker = PROFILES[index]
    require(replay.plus(plan['command'], '+TESTCASE') == name, 'testcase identity differs')
    receipt = replay.read(case / 'simulation-exit.json')
    require(receipt['executed'] is True and type(receipt['returncode']) is int and receipt['returncode'] == 0
            and receipt['timed_out'] is False and receipt['cancelled'] is False,
            'actual simulator did not complete successfully')
    require(receipt['command'] == plan['command'] and receipt['cwd'] == plan['work'], 'process command identity differs')
    _, _, _, original_elf = replay.original_command(index, member)
    require(plan['elf_sha256'] == replay.sha(original_elf), 'ELF differs from pinned historical command')
    require(replay.sha(Path(replay.plus(plan['command'], '+PRELOAD'))) == plan['elf_sha256'],
            'executed ELF bytes differ')
    replay.verify(plan['pins'])
    paths = [case / 'console.log', case / 'work/run.vcs.log', case / 'work/commit_trace.csv',
             case / 'plan.json', case / 'simulation-exit.json']
    pins = {str(p): replay.sha(p) for p in paths}
    logs = [audit_log(p.read_text(errors='strict'), requests, marker) for p in paths[:2]]
    trace = validate_trace(paths[2])
    request_insns, response_count = [], 0
    with paths[2].open() as stream:
        for row in csv.DictReader(stream):
            insn = int(row['insn'], 16)
            if row['event'] == 'cvx_req':
                require(control_instruction(insn), 'non-control vector/custom request cannot use this scope')
                request_insns.append(insn)
            elif row['event'] == 'cvx_resp':
                require(int(row['trap']) == 0, 'unexpected vector CSR exception')
                response_count += 1
            elif row['event'] == 'retire' and is_vector_instruction(insn):
                require(control_instruction(insn), 'retired vector data instruction cannot use control-only scope')
    require(len(request_insns) == response_count == requests, 'RVFI/CVXIF counts disagree')
    from run_vcs_dve_batch import valid_vdb
    vdb_files = valid_vdb(Path(plan['vdb']), replay.option(plan['command'], '-cm_name'), plan['command'][0])
    replay.verify(pins)
    return dict(status='PASS', index=index, testcase=name,
                scope='firmware selfcheck + RVFI/CVXIF trace + control-only protocol audit; not vector execution UVM signoff',
                original_uvm_errors_retained=True, scope_adjustment='nonzero backend/CVXIF traffic not applicable',
                source='existing complete current-image simulation; no rerun/no raw evidence rewrite',
                logs=logs, trace=trace, request_insns=[f'{x:08x}' for x in request_insns],
                elf_sha256=plan['elf_sha256'], pins=pins, vdb=plan['vdb'], vdb_files=vdb_files,
                coverage_test=replay.option(plan['command'], '-cm_name'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', type=Path, default=replay.ROOT / 'verification/out/full-regression-20261015-01/extensions')
    args = parser.parse_args()
    require(not args.output.exists(), 'fresh output required')
    args.output.mkdir(parents=True)
    require(replay.sha(replay.LEDGER) == replay.LEDGER_SHA, 'ledger identity drift')
    ledger = replay.read(replay.LEDGER)
    results = []
    for index in PROFILES:
        try:
            result = audit_case(args.run / f'e{index:04d}', ledger['members'][index])
        except Exception as error:
            result = dict(status='FAIL', index=index, reason=f'{type(error).__name__}: {error}')
        replay.save(args.output / f'e{index:04d}.json', result)
        results.append(result)
    replay.save(args.output / 'summary.json', dict(total=len(results),
                counts=dict(replay.Counter(r['status'] for r in results)), cases=results,
                tests_rerun=0, original_evidence_unchanged=True))
    print(json.dumps(dict(total=len(results), counts=dict(replay.Counter(r['status'] for r in results)))))
    return 0 if all(r['status'] == 'PASS' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
