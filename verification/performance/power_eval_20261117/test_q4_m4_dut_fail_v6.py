import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dut_fail_v6_tested', HERE/'q4_m4_dut_fail_v6.py')
v6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v6)


class BoundDiagnosticTests(unittest.TestCase):
    def fixture(self):
        raw = 'Core Test *** FAILED *** (tohost = 1)\nUVM_ERROR known DUT_FAIL\nUVM_ERROR : 1\n'
        classified = dict(expected_numerical_failure_records=[
            dict(line=2, kind='EXPECTED_NUMERIC_DUT_FAIL', raw='UVM_ERROR known DUT_FAIL'),
            dict(line=3, kind='ERROR_SUMMARY_ONE_DUT_FAIL', raw='UVM_ERROR : 1')])
        return raw, classified

    def test_five_diagnostics_bound_to_raw_and_fail_retained(self):
        raw, classified = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'raw.log'
            p.write_text(raw)
            expected = v6.expected_issues(p, classified)
        proof = dict(status='FAIL', issues=expected, contract_counts=dict(exceptions=0,
            protocol_errors=0, outstanding=0), elf_sha256='elf', simv_sha256='sim',
            log_sha256='raw', vector_trace_sha256='vec')
        case = dict(elf_sha256='elf')
        result = v6.check_scope(proof, expected, case, 'sim', 'raw', 'vec')
        self.assertFalse(result['full_protocol_pass'])
        self.assertEqual(proof['status'], 'FAIL')
        for issues in (expected+['AXI fault'], expected[:-1], expected[::-1],
                       [expected[0].replace('line 1', 'line 9'), *expected[1:]]):
            with self.subTest(issues=issues), self.assertRaises(ValueError):
                v6.check_scope(dict(proof, issues=issues), expected, case, 'sim', 'raw', 'vec')
        for field in ('exceptions', 'protocol_errors', 'outstanding'):
            bad = copy.deepcopy(proof)
            bad['contract_counts'][field] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                v6.check_scope(bad, expected, case, 'sim', 'raw', 'vec')
        with self.assertRaises(ValueError):
            v6.check_scope(dict(proof, status='PASS'), expected, case, 'sim', 'raw', 'vec')
        with self.assertRaises(ValueError):
            v6.check_scope(dict(proof, log_sha256='altered'), expected, case, 'sim', 'raw', 'vec')

    def test_causal_order_and_duplicate_eoc_reject(self):
        raw, classified = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'raw.log'
            p.write_text(raw+raw)
            with self.assertRaises(ValueError):
                v6.expected_issues(p, classified)
            p.write_text(raw)
            classified['expected_numerical_failure_records'][0]['line'] = 1
            with self.assertRaises(ValueError):
                v6.expected_issues(p, classified)


if __name__ == '__main__':
    unittest.main()
