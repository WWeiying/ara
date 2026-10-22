import csv
import json
import unittest

import review_akv_budget_native_evidence as review


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = review.audit.RUNS[review.audit.old.DESCRIPTOR]
        with (run/'commit_trace.csv').open() as stream:
            cls.rows = list(csv.DictReader(stream))
        cls.layout = json.loads((run/'oracle-result.json').read_text())['elf_layout']
        cls.core = (run/'trace_hart_0.log').read_text()

    def test_actual_backend_validation_not_false_zero_backend(self):
        value = review.descriptor_architecture(self.rows,self.layout,self.core)
        self.assertEqual(len(value['rejected_backend_allocation_owners']),23)
        self.assertEqual(value['precise_trap_CSR_reads'],69)
        self.assertFalse(value['full_scalar_semantics_independent'])

    def test_missing_exception_response_rejected(self):
        rows = list(self.rows)
        i = next(i for i,r in enumerate(rows) if r['event']=='cvx_resp' and r['trap']=='1')
        rows[i] = dict(rows[i],trap='0')
        with self.assertRaisesRegex(ValueError,'Incomplete rejection'):
            review.descriptor_architecture(rows,self.layout,self.core)

    def test_nonelf_retirement_rejected(self):
        rows = list(self.rows)
        i = next(i for i,r in enumerate(rows) if r['event']=='retire')
        rows[i] = dict(rows[i],insn='00000013')
        with self.assertRaisesRegex(ValueError,'Retirement not exact ELF'):
            review.descriptor_architecture(rows,self.layout,self.core)


if __name__ == '__main__': unittest.main()
