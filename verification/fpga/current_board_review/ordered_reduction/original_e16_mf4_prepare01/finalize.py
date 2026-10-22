#!/usr/bin/env python3
"""Seal software/reference evidence only after the complete offline check."""
import json
import re
import sys

sys.dont_write_bytecode = True
from prepare import HERE, CAMPAIGN, SOURCE, NAME, sha, save


def main():
    assert not (HERE / 'READY.json').exists(), 'preserve sealed READY'
    audit = json.loads((HERE / 'reference03M/audit.json').read_text())
    assert audit['status'] == 'PASS_ORIGINAL_SINGLE_REFERENCE_ONLY_PENDING_INDEPENDENT_REVIEW'
    assert audit['target_calls'] == 1 and audit['original_byte_oracle_checks'] == 144
    for path, digest in audit['evidence'].items():
        assert sha(path) == digest, path
    approval = json.loads((HERE / 'reference03M/approval.json').read_text())
    delta = json.loads((HERE / 'reference03M/CONFIG_DELTA.json').read_text())
    assert delta['exact_profile_match'] is False and delta['scalar_half_records'] == 0
    assert delta['ELF_and_resource_limits_match']
    for path, digest in approval['pins'].items():
        assert sha(path) == digest, path
    fixture_path = CAMPAIGN / 'rvv_small_redspecial02' / NAME / 'fixtures.json'
    json_fixtures = json.loads(fixture_path.read_text())
    header = SOURCE / 'fixtures.h'
    header_pairs = [[int(a, 16), int(b)] for a, b in re.findall(
        r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', header.read_text())]
    assert len(json_fixtures) == 2 and all(len(bank) == 3360 for bank in json_fixtures)
    assert sum(json_fixtures, []) == header_pairs
    evidence = {str(fixture_path): sha(fixture_path), str(header): sha(header)}
    refs = {}
    for generation in ('01', '02'):
        path = CAMPAIGN / ('rvv_small_redspecial' + generation) / 'reference_1024.json'
        obj = json.loads(path.read_text())
        selected, = [row for row in obj['results'] if row['name'] == NAME]
        refs[generation] = {'cpu_features': obj['cpu_features'], 'selected': selected}
        evidence[str(path)] = sha(path)
    assert refs['01']['selected']['exit_code'] == 132
    assert 'Illegal instruction' in refs['01']['selected']['output']
    assert refs['02']['selected']['exit_code'] == 0 and refs['02']['selected']['passed']
    assert refs['02']['cpu_features'] == ['zfh=true', 'zvfh=true']
    original = CAMPAIGN / 'rvv_fp16_redspecial01/overlay/opt/ara-tests/rvv_fp_redspecial_e16_mf4'
    assert sha(original) == sha(SOURCE / 'original.elf')
    evidence[str(original)] = sha(original)
    save(HERE / 'source_supplement.json', {
        'all_fixture_header_JSON_pairs_equal': 6720,
        'selected_bank1_row1545': json_fixtures[1][1545],
        'distinct_bank0_row1545': json_fixtures[0][1545],
        'historical_reference_environment': refs,
        'early01_scope': 'default QEMU FP16 illegal instruction, not RTL failure',
        'original_campaign_ELF_equals_handoff': True, 'pins': evidence})
    pins = dict(approval['pins'])
    pins.update(delta['pins'])
    pins[delta['cost_review']['path']] = delta['cost_review']['sha256']
    pins.update(evidence)
    for path in HERE.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            pins[str(path)] = sha(path)
    save(HERE / 'READY.json', {
        'status': 'REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW',
        'scope': 'single archived e16/mf4/VL8 scenario3/l4/mode3/frm0/op0/sticky0',
        'original_selector': 'unchanged; all surrounding scalar loops retained',
        'sourceproof': str(HERE / 'sourceproof.json'),
        'reference': str(HERE / 'reference03M/audit.json'),
        'profile_delta': str(HERE / 'reference03M/CONFIG_DELTA.json'),
        'exact_profile_contract_PASS': False,
        'host_original_C': 'PASS_13: positive +12 injected failures',
        'host_raw_checker': 'PASS_15: positive +14 witness corruptions',
        'old1M': 'NOT_RUN_STATIC_BOUND_INSUFFICIENT',
        'reference_executions': 1, 'reference_resource_revision': 'explicit user pre-execution authorization',
        'firmware_retired_to_HTIF': audit['firmware_retired_to_HTIF'],
        'elapsed_s': audit['elapsed_s'],
        'soc_ELF': {'path': str(HERE / 'soc/program.elf'), 'sha256': sha(HERE / 'soc/program.elf')},
        'spike_ELF': {'path': str(HERE / 'spike/program.elf'), 'sha256': sha(HERE / 'spike/program.elf')},
        'VCS_started': False, 'RTL_build': False, 'DUT_accepted': False,
        'full6720_Linux_accepted': False, 'pins': pins})


if __name__ == '__main__':
    main()
