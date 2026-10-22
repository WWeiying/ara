import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('failure_successors', HERE / 'run_failure_replays_20261015.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize('change', [
    {'returncode': 1}, {'returncode': None}, {'returncode': False},
    {'timed_out': True}, {'cancelled': True}, {'executed': False},
])
def test_no_success_without_actual_completed_zero_wait(monkeypatch, tmp_path, change):
    receipt = dict(executed=True, returncode=0, timed_out=False, cancelled=False)
    receipt.update(change)
    monkeypatch.setattr(m.prior, 'read', lambda _: receipt)
    monkeypatch.setattr(m.prior, 'check_case', lambda _: pytest.fail('must not enter semantic check'))
    with pytest.raises(ValueError, match='actual simulator'):
        m.check(dict(directory=str(tmp_path)))


def test_exact_bounded_successors():
    assert m.BUDGETS == {'c0375': 600, 'e0784': 1200}


def test_numeric_exit_is_retained_when_checker_throws(monkeypatch, tmp_path):
    actual = dict(executed=True, returncode=0, timed_out=False, cancelled=False, elapsed_s=10)
    monkeypatch.setattr(m.prior, 'child', lambda *a, **kw: actual)
    monkeypatch.setattr(m, 'check', lambda _: (_ for _ in ()).throw(ValueError('semantic mismatch')))
    plan = dict(name='c0375', directory=str(tmp_path), work=str(tmp_path), command=['simv'],
                pins={}, timeout_s=600)
    updates = []
    result = m.run_case(plan, updates.append)
    assert result['status'] == 'FAIL'
    assert result['actual_process_wait']['returncode'] == 0
    assert 'semantic mismatch' in result['reason']
