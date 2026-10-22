#!/usr/bin/env python3
"""Original URED end gate, with explicit frozen missing-report qualification.

The original independent backend predicates remain mandatory. Missing UVM final
reports are not silently converted to PASS; their exact diagnostics are retained,
and the separate complete architecture and reset/AXI waveform proofs are required.
"""
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_pending_fpu_ured_uvm_20261016 as predecessor
from audit_probe_semantics_20261015 import require, save, sha

base, ROOT = predecessor.base, predecessor.ROOT
MISSING_REPORT_ISSUES = frozenset((
    'expected one UVM CVXIF summary, found 0',
    'dedicated reset test lacks one matching trigger and observed reset',
    'UVM error/fatal report summary is missing or nonzero',
    'UVM did not complete its check/report phases',
    'expected one backend VID summary, found 0',
    'expected one Ara AXI read summary, found 0',
))


def ured_endgate(a, checker=None):
    import run_vmfpu_ured_reset763 as original
    from ara_verify import uvm_dut
    a.bind(__file__)
    a.bind(ROOT / 'verification/tests/test_audit_pending_fpu_ured_uvm_v2_20261016.py')
    check = checker or original.audit.events.run.reset.check_real_uvm_log
    def capture(path, **kwargs):
        value = check(path, **kwargs)
        save(a.out / 'mandatory-uvm-proof.json', value)
        return value
    state = base.execute_block(a, 'mandatory-uvm-endgate', original.collect,
        'uvm=reset.check_real_uvm_log(', 'book=life.read_bound(',
        dict(reset=SimpleNamespace(check_real_uvm_log=capture), RUN=base.CurrentView(a)))
    uvm = state['uvm']
    left, right = uvm['uvm_backend_event_sha256'], uvm['vector_backend_event_sha256']
    require(isinstance(left, str) and re.fullmatch('[0-9a-f]{64}', left) is not None
            and left == right, 'Actual nonempty independent backend digests required')
    require(type(uvm['uvm_backend_event_count']) is int
            and uvm['uvm_backend_event_count'] == uvm['vector_backend_event_count'] > 0,
            'Actual equal positive independent backend event counts required')
    logs = (a.out / 'runtime/run.vcs.log').read_text()
    severities = uvm_dut._SEVERITY.findall(logs)
    require(not re.search(r'(?m)^UVM_(?:ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]', logs)
            and not any(int(v) for _, v in severities), 'Actual UVM severity/protocol error')
    if uvm['status'] != 'PASS':
        require(uvm['status'] == 'FAIL' and len(uvm['issues']) == len(MISSING_REPORT_ISSUES)
                and set(uvm['issues']) == MISSING_REPORT_ISSUES,
                'Unexpected independent UVM diagnostic; not the exact frozen missing-report scope')
        # The generic issue aliases missing and nonzero summaries. Only actual
        # absence is qualified here; zero/nonzero or malformed records cannot hide.
        require(not severities and '[TEST_DONE]' not in logs
                and re.search(r'(?m)^\s*UVM_(?:ERROR|FATAL)\s*:', logs) is None,
                'Missing-report qualification requires truly absent severity/final reports')
    else:
        require(not uvm['issues'], 'PASS UVM status with diagnostic issues')
    architecture = json.loads((a.out / 'architecture-status.json').read_text())
    wave = json.loads((a.out / 'reset-wave/audit.json').read_text())
    require(architecture['status'] == wave['status'] == 'PASS' and wave['required_for_case'] is True,
            'Complete architecture and original external-reset/AXI waveform required')
    proof = dict(status='PASS', original_endgate_preserved=True, require_events=True,
        require_backend=True, require_axi=True, reset_kind='state',
        vector_trace=str(a.work / 'vector_trace.csv'),
        independent_backend_digests_equal=True, positive_backend_events=uvm['uvm_backend_event_count'],
        contract_counts=uvm['contract_counts'], result=str(a.out / 'mandatory-uvm-proof.json'),
        uvm_checker_status=uvm['status'], original_diagnostics=uvm['issues'],
        missing_report_scope_explicit=uvm['status'] != 'PASS', UVM_report_PASS_claimed=False,
        actual_severity_summary_records=severities,
        substitute_for_missing_report='No fabricated UVM summary: original per-epoch architecture/events and full four-clock/controller/all-AXI waveform checked separately')
    save(a.out / 'mandatory-uvm-status.json', proof)
    return proof


def main():
    predecessor.ured_endgate = ured_endgate
    predecessor.main()
    # Only newly generated successor outputs are extended; all predecessor
    # reports, adapters, and the 33 reused per-case input pins remain untouched.
    output = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
    pins = json.loads((output / 'checker-code-pins.json').read_text())
    for path in (Path(__file__).resolve(), ROOT / 'verification/tests/test_audit_pending_fpu_ured_uvm_v2_20261016.py'):
        pins[str(path)] = sha(path)
    save(output / 'checker-code-pins.json', pins)
    result = json.loads((output / 'audit.json').read_text())
    result['original_URED_endgate_preserved'] = True
    result['full_UVM_report_PASS_claimed'] = False
    save(output / 'audit.json', result)


if __name__ == '__main__':
    main()
