"""Original gate plus narrowly evidenced report-absence policy, no fake UVM PASS."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import audit_pending_fpu_ured_uvm_v2_20261016 as audit


class OriginalUredEndgateTests(unittest.TestCase):
    def fixture(self):
        return dict(status='FAIL', issues=sorted(audit.MISSING_REPORT_ISSUES),
            uvm_backend_event_sha256='1'*64, vector_backend_event_sha256='1'*64,
            uvm_backend_event_count=204, vector_backend_event_count=204,
            contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0))

    def run_gate(self, value, log=''):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); (out / 'runtime').mkdir(); (out / 'reset-wave').mkdir()
            (out / 'runtime/run.vcs.log').write_text(log)
            (out / 'architecture-status.json').write_text(json.dumps(dict(status='PASS')))
            (out / 'reset-wave/audit.json').write_text(json.dumps(dict(status='PASS', required_for_case=True)))
            a = SimpleNamespace(out=out, work=Path('/actual/current/work'), bind=lambda p: Path(p))
            calls = []
            def check(path, **kwargs):
                calls.append((path, kwargs)); return copy.deepcopy(value)
            try:
                result = audit.ured_endgate(a, check)
                self.assertEqual(calls, [(out / 'runtime/run.vcs.log', dict(require_events=True,
                    require_backend=True, require_axi=True, vector_trace=a.work / 'vector_trace.csv', reset_kind='state'))])
                return result
            finally:
                self.assertEqual(json.loads((out / 'mandatory-uvm-proof.json').read_text()), value)

    def test_original_scope_pass_preserves_raw_fail_and_no_uvm_report_claim(self):
        result = self.run_gate(self.fixture())
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['uvm_checker_status'], 'FAIL')
        self.assertFalse(result['UVM_report_PASS_claimed'])

    def test_null_missing_malformed_or_mismatched_backend_rejected(self):
        for left, right in ((None, None), ('', ''), ('not-a-digest', 'not-a-digest'), ('1'*64, '2'*64)):
            with self.subTest(left=left), self.assertRaises(ValueError):
                value = self.fixture(); value.update(uvm_backend_event_sha256=left, vector_backend_event_sha256=right)
                self.run_gate(value)

    def test_zero_mismatched_backend_counts_and_each_nonzero_contract_rejected(self):
        for key in ('uvm_backend_event_count', 'vector_backend_event_count'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                value = self.fixture(); value[key] = 0; self.run_gate(value)
        for key in ('exceptions', 'protocol_errors', 'outstanding'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                value = self.fixture(); value['contract_counts'][key] = 1; self.run_gate(value)

    def test_extra_backend_or_axi_diagnostic_rejected(self):
        for issue in ('UVM and independent backend VID events disagree across reset epochs',
                      'Ara AXI read bursts remain outstanding'):
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                value = self.fixture(); value['issues'].append(issue); self.run_gate(value)

    def test_real_nonzero_zero_or_malformed_severity_record_not_absence(self):
        for log in ('UVM_ERROR : 1\n', 'UVM_FATAL : 1\n', 'UVM_ERROR : 0\n', 'UVM_ERROR : invalid\n',
                    'UVM_FATAL actual runtime error\n'):
            with self.subTest(log=log), self.assertRaises(ValueError):
                self.run_gate(self.fixture(), log)

    def test_actual_checker_missing_backend_log_rejected(self):
        from ara_verify.uvm_dut import check_real_uvm_log
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.log'; path.write_text('')
            result = check_real_uvm_log(path, require_events=True, require_backend=True, require_axi=True, reset_kind='state')
        with self.assertRaises((ValueError, TypeError)):
            self.run_gate(result)


if __name__ == '__main__':
    unittest.main()
