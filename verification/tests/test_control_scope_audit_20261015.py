import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('control_scope', HERE / 'control_scope_audit_20261015.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def log(requests=0):
    ids = ['VID/NO_TRAFFIC'] if requests else ['CVXIF/NO_TRAFFIC', 'VID/NO_TRAFFIC']
    return '\n'.join([
        'firmware checks=10 failures=0',
        'Core Test *** SUCCESS *** (tohost = 0)',
        f'UVM_INFO [CVXIF/COUNT] observed requests={requests} responses={requests} aborted=0 reused=0 immediate={requests}',
        'UVM_INFO [VID/COUNT] allocations=0 completions=0 aborted=0 max_live=0',
        *[f'UVM_ERROR /source/ara_cvxif_uvm_pkg.sv(504) @ 120: uvm_test_top [{i}] {m.ERROR_TEXT[i]}' for i in ids],
        f'UVM_ERROR : {len(ids)}',
        'UVM_FATAL : 0',
        f'[ARA_CONTRACT] requests={requests} responses={requests} exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0',
    ])


@pytest.mark.parametrize('requests', [0, 1, 20, 42])
def test_exact_control_only_accounting(requests):
    assert m.audit_log(log(requests), requests, 'firmware checks=10 failures=0')['protocol']['requests'] == requests


@pytest.mark.parametrize('extra', [
    'UVM_ERROR /source/ara_cvxif_uvm_pkg.sv(500) @ 120: uvm_test_top [CVXIF/DUP_ID] wrong id',
    'Fatal: actual failure', 'FAIL: bad result', 'result failures=1',
    'UVM_FATAL : 1', '[ARA_CONTRACT_ERROR] payload changed',
])
def test_rejects_real_errors_even_after_firmware_success(extra):
    with pytest.raises(ValueError):
        m.audit_log(log() + '\n' + extra, 0, 'firmware checks=10 failures=0')


def test_rejects_missing_diagnostic_or_wrong_summary():
    for changed in [log().replace('UVM_ERROR : 2', 'UVM_ERROR : 0'),
                    log().replace('allocations=0', 'allocations=1'),
                    log().replace('protocol_errors=0', 'protocol_errors=1'),
                    log().replace('requests=0 responses=0 aborted=0', 'requests=1 responses=0 aborted=0'),
                    log().replace('Core Test *** SUCCESS ***', 'not complete')]:
        with pytest.raises(ValueError):
            m.audit_log(changed, 0, 'firmware checks=10 failures=0')


def test_rejects_duplicate_firmware_check_count():
    with pytest.raises(ValueError):
        m.audit_log(log() + '\nfirmware checks=10 failures=0', 0, 'firmware checks=10 failures=0')


def test_control_scope_cannot_accept_vector_data_or_custom_instructions():
    assert m.control_instruction(0xc2002073)
    assert not m.control_instruction(0x02000057)
    assert not m.control_instruction(0x0000005b)
    assert not m.control_instruction(0x02006007)
    assert not m.control_instruction(0x30002073)
