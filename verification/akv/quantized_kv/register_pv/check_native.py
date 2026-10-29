"""Reuse strict complete-call ABBA checks with an explicit experiment identity."""
from pathlib import Path
import sys

PREFILL = Path(__file__).resolve().parent.parent / 'prefill'
sys.path.insert(0, str(PREFILL))
from check_selector_native import check_log as check_pair


def check_log(text, golden, q4):
    marker = 'REGISTER_PV_BINDINGS value=shared_rvv_q8_0 baseline=current_shared candidate=register_pv'
    if text.splitlines().count(marker) != 1 or 'SELECTOR_' in text:
        raise ValueError('Wrong experiment identity')
    measured = check_pair(text.replace('REGISTER_PV_', 'SELECTOR_'), golden, q4,
                          mode_field='candidate')
    measured.update(scope='Complete Decode call, shared RVV versus register-PV; not whole model',
                    comparison='shared_rvv_vs_register_pv', value_rows_per_trial=20)
    return measured
