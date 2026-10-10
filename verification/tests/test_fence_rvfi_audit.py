import copy
import csv
import io
import json
from pathlib import Path
import unittest

import fence_rvfi_audit as audit

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'verification/out/gap36-fence-20261004-01'
TRACE = (ROOT / 'verification/out/gap36-fence-current-20261004-02/results/'
         'fence_t_gap36_smoke/tests/app_fence_t_gap36_smoke/commit_trace.csv')


class FenceRvfiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = json.loads((BUILD / 'elf_metadata.json').read_text())[0]
        cls.blob = (BUILD / 'fence_t_gap36_smoke.elf').read_bytes()
        cls.sites = json.loads((BUILD / 'precheck.json').read_text())['elf_audit']['sites']
        cls.text = TRACE.read_text()
        cls.rows = audit.parse_trace(cls.text)
        cls.fence = next(i for i, r in enumerate(cls.rows) if r['insn'] == 0xb)

    def evaluate(self, rows):
        return audit.audit_rows(rows, self.metadata, self.blob, self.sites)

    def test_recorded_rvfi(self):
        result = self.evaluate(self.rows)
        self.assertEqual(result['capture_stores_checked'], 130)
        self.assertEqual(result['retired_records'], 11526)

    def reject_mutation(self, index, key, value):
        rows = copy.deepcopy(self.rows)
        rows[index][key] = value
        with self.assertRaises(ValueError):
            self.evaluate(rows)

    def test_wrong_opcode(self):
        self.reject_mutation(self.fence, 'insn', 0x13)

    def test_skipped_resume(self):
        self.reject_mutation(self.fence + 1, 'pc', self.rows[self.fence + 2]['pc'])

    def test_wrong_gpr_data(self):
        self.reject_mutation(self.fence + 1, 'mem_wdata', 0)

    def test_wrong_store_address(self):
        self.reject_mutation(self.fence + 1, 'mem_addr', 0)

    def test_wrong_store_mask(self):
        self.reject_mutation(self.fence + 1, 'mem_wmask', 15)

    def test_wrong_auipc_result(self):
        self.reject_mutation(self.fence + 2, 'rd_wdata', 0)

    def test_wrong_auipc_destination(self):
        self.reject_mutation(self.fence + 2, 'rd', 0)

    def test_wrong_fp_data(self):
        i = next(i for i in range(self.fence + 1, self.fence + 68)
                 if self.rows[i]['insn'] & 0x7f == 0x27)
        self.reject_mutation(i, 'mem_wdata', 0)

    def test_duplicate_fence(self):
        rows = copy.deepcopy(self.rows)
        rows.insert(self.fence + 1, rows[self.fence])
        with self.assertRaises(ValueError):
            self.evaluate(rows)

    def test_duplicate_capture(self):
        rows = copy.deepcopy(self.rows)
        rows.extend(rows[self.fence + 1:self.fence + 3])
        with self.assertRaises(ValueError):
            self.evaluate(rows)

    def test_truncated_capture(self):
        with self.assertRaises(ValueError):
            self.evaluate(self.rows[:self.fence + 2])

    def test_trap_rejected(self):
        self.assertRaises(ValueError, audit.parse_trace, self.text.replace(',0\n', ',1\n', 1))

    def test_missing_order(self):
        lines = self.text.splitlines()
        self.assertRaises(ValueError, audit.parse_trace, '\n'.join(lines[:2] + lines[3:]))

    def test_duplicate_order(self):
        lines = self.text.splitlines()
        self.assertRaises(ValueError, audit.parse_trace, '\n'.join(lines[:2] + lines[1:]))


if __name__ == '__main__':
    unittest.main()
