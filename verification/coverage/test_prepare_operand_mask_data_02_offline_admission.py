"""Negative gates prevent timeout, incomplete VDB and partial vector admission."""
from pathlib import Path
import tempfile
import unittest

import prepare_operand_mask_data_02_offline_admission as p


class AdmissionGateTests(unittest.TestCase):
    def test_timeout_and_nonzero_exit_rejected(self):
        for state in ({'status': 'SIMULATION_NOT_ADMITTED', 'reason': 'TimeoutExpired:'},
                      {'status': 'SIMULATION_EXITED_NOT_ADMITTED', 'returncode': 1},
                      {'status': 'SIMULATION_EXITED_NOT_ADMITTED', 'returncode': 0, 'timeout': True}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                p.normal_exit(state)

    def test_normal_exit_only(self):
        p.normal_exit(dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0,
                           coverage_admitted=False, admission_performed=False))

    def test_original_mode64_not_native_end(self):
        with self.assertRaises(ValueError):
            p.vdb_end(p.q.RUN / 'code.vdb', [])

    def test_incomplete_architecture_hold_rejected(self):
        for result in ({}, {'full_architecture_qualified': False},
                       {'full_architecture_qualified': True, 'full_vector': {'status': 'PREFIX'}}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                p.architecture_gate(result)

    def test_incomplete_test_xml_rejected(self):
        with tempfile.TemporaryDirectory(dir=p.OUT) as name:
            root = Path(name)
            test = root / 'snps/coverage/db/testdata/operand_mask_full_width_data'
            test.mkdir(parents=True)
            (test / 'line.verilog.data.xml').write_text('<covdata>')
            with self.assertRaises(Exception):
                p.vdb_end(root, [])


if __name__ == '__main__':
    unittest.main()
