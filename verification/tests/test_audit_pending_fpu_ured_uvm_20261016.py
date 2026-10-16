"""Negative tests execute the original URED end-gate statements unchanged."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import audit_pending_fpu_ured_uvm_20261016 as successor


class UredMandatoryEndgateTests(unittest.TestCase):
    def run_gate(self, value):
        with tempfile.TemporaryDirectory() as directory:
            a = SimpleNamespace(out=Path(directory), work=Path('/actual/current/work'), bind=lambda p: Path(p))
            calls = []
            def checker(path, **kwargs):
                calls.append((path, kwargs))
                return copy.deepcopy(value)
            result = successor.ured_endgate(a, checker)
            self.assertEqual(calls, [(a.out / 'runtime/run.vcs.log', dict(require_events=True,
                require_backend=True, require_axi=True, vector_trace=a.work / 'vector_trace.csv', reset_kind='state'))])
            return result

    def fixture(self):
        return dict(status='PASS', uvm_backend_event_sha256='same', vector_backend_event_sha256='same',
                    contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0))

    def test_original_full_gate_and_exact_checker_arguments(self):
        self.assertEqual(self.run_gate(self.fixture())['status'], 'PASS')

    def test_clean_frontend_cannot_hide_backend_digest_mismatch(self):
        value = self.fixture(); value['uvm_backend_event_sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'Lifecycle/protocol differs'):
            self.run_gate(value)

    def test_each_nonzero_terminal_contract_counter_rejected(self):
        for key in ('exceptions', 'protocol_errors', 'outstanding'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Lifecycle/protocol differs'):
                value = self.fixture(); value['contract_counts'][key] = 1
                self.run_gate(value)

    def test_missing_backend_axi_or_status_fails_closed(self):
        value = self.fixture(); del value['vector_backend_event_sha256']
        with self.assertRaises(KeyError):
            self.run_gate(value)
        value = self.fixture(); value['status'] = 'CHECKER_REQUIRED'
        with self.assertRaisesRegex(ValueError, 'must pass'):
            self.run_gate(value)


if __name__ == '__main__':
    unittest.main()
