"""Host tests: numeric DUT_FAIL is scoped, never a generic UVM/protocol exemption."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dut_fail_v5_tested', HERE/'q4_m4_dut_fail_v5.py')
v5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v5)


class DutFailTests(unittest.TestCase):
    source = Path('/frozen/ara_cvxif_uvm_pkg.sv')

    def text(self):
        return ('OPQ_DONE errors=4\nCore Test *** FAILED *** (tohost = 1)\n'
            'UVM_ERROR /frozen/ara_cvxif_uvm_pkg.sv(628) @ 99: uvm_test_top '
            '[CVXIF/DUT_FAIL] real Ara program did not report success\n'
            '--- UVM Report Summary ---\nUVM_ERROR : 1\nUVM_FATAL : 0\n[CVXIF/DUT_FAIL] 1\n')

    def scan(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'raw.log'
            path.write_text(text)
            return v5.scan(path, self.source, 628)

    def test_known_error_preserved_as_evidence_not_rewritten_to_success(self):
        view, report = self.scan(self.text())
        self.assertIn('Core Test *** FAILED ***', view)
        self.assertNotIn('SUCCESS', view)
        self.assertEqual(len(report['expected_numerical_failure_records']), 2)
        self.assertIn('UVM_ERROR', report['expected_numerical_failure_records'][0]['raw'])
        self.assertFalse(report['raw_log_modified'])
        self.assertFalse(report['synthesized_records'])

    def test_unknown_extra_missing_and_wrong_counts_reject(self):
        text = self.text()
        for old, new in (('CVXIF/DUT_FAIL', 'VID/NO_TRAFFIC'), ('(628)', '(627)'),
                         ('/frozen/', '/other/'), ('UVM_ERROR : 1', 'UVM_ERROR : 2'),
                         ('UVM_ERROR : 1', 'UVM_ERROR : 0'), ('UVM_FATAL : 0', 'UVM_FATAL : 1'),
                         ('[CVXIF/DUT_FAIL] 1', '[CVXIF/DUT_FAIL] 2'),
                         ('OPQ_DONE errors=4\n', ''), ('tohost = 1', 'tohost = 2')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.scan(text.replace(old, new))
        for extra in ('UVM_ERROR another event\n', 'UVM_FATAL event\n', 'Error: bad\n',
                      'Assertion failed\n', 'TIMEOUT\n', text):
            with self.subTest(extra=extra[:30]), self.assertRaises(ValueError):
                self.scan(text+extra)

    def test_protocol_fail_not_reclassified_pass(self):
        case = dict(elf_sha256='elf')
        proof = dict(status='FAIL', issues=[v5.PROTOCOL_ISSUE],
            contract_counts=dict(exceptions=0, protocol_errors=0, outstanding=0),
            elf_sha256='elf', simv_sha256='sim', log_sha256='raw', vector_trace_sha256='vec')
        result = v5.protocol_scope(proof, case, 'sim', 'raw', 'vec')
        self.assertFalse(result['full_protocol_pass'])
        self.assertEqual(proof['status'], 'FAIL')
        for field, value in (('status', 'PASS'), ('issues', []),
                             ('issues', [v5.PROTOCOL_ISSUE, 'AXI failure']), ('log_sha256', 'rewritten')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                v5.protocol_scope(dict(proof, **{field: value}), case, 'sim', 'raw', 'vec')
        for field in ('exceptions', 'protocol_errors', 'outstanding'):
            bad = copy.deepcopy(proof)
            bad['contract_counts'][field] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                v5.protocol_scope(bad, case, 'sim', 'raw', 'vec')


if __name__ == '__main__':
    unittest.main()
