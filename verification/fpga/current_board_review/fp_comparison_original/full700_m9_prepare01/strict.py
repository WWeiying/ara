"""Private instance of sealed audit logic, bound to local source-derived model700."""
import importlib.util
from newscope import PREVIOUS, BOUND
from model import require

_spec = importlib.util.spec_from_file_location('sealed_fp_strict700_instance', PREVIOUS / 'strict.py')
_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_old)
specification, spike_rows, VETO = _old.specification, _old.spike_rows, _old.VETO


def audit(rows, spec, spike_vectors=False, abort=None):
    result = _old.audit(rows, spec, spike_vectors, abort)
    require(result['target_calls'] == BOUND and result['full_result_bit_checks'] == BOUND*512
            and result['guard_checks'] == BOUND*2, 'Exact700 scope')
    result['status'] = 'FULL_ORIGINAL700_STRICT_ACCEPTED_NOT_FULL_PARENT'
    result['immutable_audit_reuse'] = str(PREVIOUS / 'strict.py')
    return result
