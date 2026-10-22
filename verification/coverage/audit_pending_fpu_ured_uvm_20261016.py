#!/usr/bin/env python3
"""Successor restores URED's mandatory independent UVM/backend end gate.

Recheck only 660 (independently anchored gold) and 764 (architecture, waveform,
and original UVM end gate). Preserve all frozen adapters and other 33 reports.
"""
import argparse
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_pending_fpu_20261016 as base
import audit_pending_fpu_red32_reference_20261016 as reference
from audit_probe_semantics_20261015 import read, require, save, sha, install_guard

ROOT = base.ROOT


def ured_endgate(a, checker=None):
    import run_vmfpu_ured_reset763 as original
    reset = original.audit.events.run.reset
    if checker is not None:
        reset = SimpleNamespace(check_real_uvm_log=checker)
    state = base.execute_block(a, 'mandatory-uvm-endgate', original.collect,
        'uvm=reset.check_real_uvm_log(', 'book=life.read_bound(',
        dict(reset=reset, RUN=base.CurrentView(a)))
    uvm = state['uvm']
    require(uvm['status'] == 'PASS', 'Original independent UVM audit must pass')
    save(a.out / 'mandatory-uvm-proof.json', uvm)
    proof = dict(status='PASS', original_endgate_preserved=True,
        require_events=True, require_backend=True, require_axi=True, reset_kind='state',
        vector_trace=str(a.work / 'vector_trace.csv'),
        independent_backend_digests_equal=uvm['uvm_backend_event_sha256'] == uvm['vector_backend_event_sha256'],
        contract_counts=uvm['contract_counts'], result=str(a.out / 'mandatory-uvm-proof.json'))
    save(a.out / 'mandatory-uvm-status.json', proof)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-audit', type=Path,
        default=ROOT / 'verification/out/pending-fpu-audit-20261016-final01/audit.json')
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'verification/out') and not output.exists(), 'Fresh successor output required')
    old = read(args.base_audit)
    require(len(old['cases']) == 35 and {r['index'] for r in old['cases']} == set(base.CASES),
            'Complete frozen predecessor required')
    install_guard(output)
    output.mkdir()
    old_exact, old_reset = base.red32_exact, base.reset_architecture
    test = ROOT / 'verification/tests/test_audit_pending_fpu_ured_uvm_20261016.py'
    def pin_successor(a):
        a.bind(__file__)
        a.bind(test)
    def anchored(a, *rest):
        pin_successor(a)
        reference.authenticate(a)
        return old_exact(a, *rest)
    def complete_reset(a):
        pin_successor(a)
        value = old_reset(a)
        value['mandatory_independent_uvm_endgate'] = ured_endgate(a)
        return value
    base.red32_exact, base.reset_architecture = anchored, complete_reset
    replacements = {index: base.audit_one(index, output) for index in (660, 764)}
    pins = {str(args.base_audit.resolve()): sha(args.base_audit), str(Path(__file__).resolve()): sha(__file__),
            str(test): sha(test)}
    rows = []
    for row in old['cases']:
        selected = replacements.get(row['index'], row)
        report = Path(selected['report'])
        require(report.is_absolute() and report.is_relative_to(ROOT / 'verification/out'), 'Absolute owned report required')
        actual = read(report)
        require(actual['index'] == selected['index'] and actual['status'] == selected['status'], 'Summary/report differs')
        if actual['status'] == 'PASS':
            require(actual['execution_identity'] is not None and actual['semantic']['status'] == 'PASS',
                    'Actual execution and complete architecture required')
            if row['index'] in base.RESET_CASES:
                require(actual['semantic']['microstructure_witness']['status'] == 'PASS', 'Mandatory reset waveform required')
            if row['index'] == 764:
                require(actual['semantic']['mandatory_independent_uvm_endgate']['status'] == 'PASS',
                        'Mandatory independent UVM end gate required')
        pins[str(report)] = sha(report)
        rows.append(selected)
    codes = read(ROOT / 'verification/out/pending-fpu-audit-tests-20261016-01/frozen-code-pins.json')
    codes.update({str(Path(__file__).resolve()): sha(__file__), str(test): sha(test)})
    require(all(sha(path) == digest for path, digest in codes.items()), 'Frozen adapter/helper code drift')
    save(output / 'checker-code-pins.json', codes)
    result = dict(cases=rows, accepted=[r['index'] for r in rows if r['status'] == 'PASS'],
        rejected=[r['index'] for r in rows if r['status'] == 'FAIL'],
        checker_required=[r['index'] for r in rows if r['status'] == 'CHECKER_REQUIRED'],
        summary_input_pins=pins, checker_code_pins=str(output / 'checker-code-pins.json'),
        replaced_cases=[660, 764], preserved_cases=33, preserved_predecessor=str(args.base_audit.resolve()),
        independent_review_finding='Restored original URED independent backend digest equality and zero exception/protocol/outstanding UVM end gate',
        RTL_simulation_runs=0, coverage_admitted=False)
    save(output / 'audit.json', result)
    print('Final', len(result['accepted']), 'PASS;', result['rejected'], 'FAIL;', result['checker_required'], 'CHECKER_REQUIRED', flush=True)


if __name__ == '__main__':
    main()
