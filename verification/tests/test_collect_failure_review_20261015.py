import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('review_collection', HERE / 'collect_failure_review_20261015.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_clean_runtime_or_echo_removal_is_not_an_architecture_pass():
    assert not m.probe_accepted(dict(index=782, status='CHECKER_REQUIRED',
                                    components={'execution': {'status': 'PASS'}}))


def test_false_pass_claim_with_missing_native_oracle_is_rejected():
    with pytest.raises(ValueError):
        m.probe_accepted(dict(index=782, status='CHECKER_REQUIRED', functional_status='PASS',
                             components={'execution': {'status': 'PASS'}}))


def test_control_probe_needs_full_scalar_and_zero_vector_checks():
    value = dict(index=786, status='CHECKER_REQUIRED', functional_status='PASS',
                 components={k: {'status': 'PASS'} for k in ('execution', 'native', 'dispatch')})
    with pytest.raises(ValueError):
        m.probe_accepted(value)
    value['components'].update({k: {'status': 'PASS'} for k in ('scalar', 'vector')})
    assert m.probe_accepted(value)


def test_missing_old_internal_toggle_witness_does_not_fabricate_its_success():
    value = dict(index=782, status='CHECKER_REQUIRED', functional_status='PASS',
                 components={k: {'status': 'PASS'} for k in ('execution', 'native', 'dispatch')},
                 micro_witness_status='NOT_PORTABLE')
    assert m.probe_accepted(value)
    assert value['micro_witness_status'] == 'NOT_PORTABLE'
