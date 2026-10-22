import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1] / 'coverage'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('fresh_full_replay',
                                             HERE / 'run_full_regression_20261015.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def test_dispatches_entire_selection_without_fail_fast_functional_gate(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(entry.core, 'original_schedule',
                        lambda output, names, jobs: calls.append((output, names, jobs)))
    names = ['formerly-failing', 'remaining-test']
    entry.schedule_all(tmp_path, names, 8)
    assert calls == [(tmp_path, names, 8)]
    policy = entry.core.read(tmp_path / 'dispatch-policy.json')
    assert policy['original_oracles_unchanged'] is True
    assert policy['retry'] is False
    assert policy['gate_barrier'] is False


def test_rejects_unreviewed_worker_count(tmp_path):
    with pytest.raises(ValueError, match='eight workers'):
        entry.schedule_all(tmp_path, ['case'], 9)


def test_rejects_incomplete_798_inventory(monkeypatch):
    def read(path):
        if path == entry.HISTORY:
            return {'cases': []}
        return {'ledger_members': 798, 'members': []}
    monkeypatch.setattr(entry.core, 'read', read)
    with pytest.raises(ValueError, match='798-member'):
        entry.inventory()


def test_rejects_non600_core_inventory(monkeypatch):
    def read(path):
        if path == entry.HISTORY:
            return {'cases': []}
        return {'ledger_members': 798, 'members': [{}] * 798}
    monkeypatch.setattr(entry.core, 'read', read)
    with pytest.raises(ValueError, match='600 core'):
        entry.inventory()
