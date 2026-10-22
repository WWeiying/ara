"""Offline exact-native-format and trap mutation tests; no simulator."""
import copy
from pathlib import Path
import unittest

import audit_fof_repair_v3 as checker

CASE = checker.base.ROOT / 'verification/out/failed-repair-acceptance-20261008-04/results/vgap112_sv39_fof'


class NativeTracer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.symbols = json.loads((checker.base.PRE / 'symbols.json').read_text())
        cls.rows = checker.base.common.read_csv((CASE/'commit_trace.csv').read_bytes(),
                                              checker.base.common.COMMIT_FIELDS)
        cls.text = (CASE/'trace_hart_0.log').read_text()
        cls.header = next(line for line in cls.text.splitlines() if line.startswith('Exception @'))

    def check(self, text=None, rows=None):
        return checker.tracer_exact(self.text if text is None else text,
                                    self.rows if rows is None else rows, self.symbols)

    def test_actual_no_tval_positive(self):
        result = self.check()
        self.assertEqual(result['nontrap_retirements'],83732)
        self.assertEqual(result['handler_mtval_read_cycle'],55150)
        self.assertEqual(result['handler_mtval_store_cycle'],55159)

    def test_sealed_checker_reproduces_false_failure(self):
        with self.assertRaisesRegex(ValueError,'cause/PC/tval'):
            checker.base.tracer_exact(self.text,self.rows,self.symbols)

    def test_missing_or_duplicate_header(self):
        for replacement in ('',self.header+'\n'+self.header):
            with self.assertRaises(ValueError):self.check(self.text.replace(self.header,replacement))

    def test_wrong_pc_cause_or_malformed(self):
        for replacement in (self.header.replace('800021c8','8000213c'),
                            self.header.replace('Environment Call Supervisor Mode','Load Page Fault'),
                            self.header.replace('Supervisor','Machine'),self.header+','):
            with self.assertRaises(ValueError):self.check(self.text.replace(self.header,replacement))

    def test_unexpected_tval_not_ignored(self):
        for value in ('0000000000000000','0000000000000001','xxxxxxxxxxxxxxxx'):
            with self.assertRaises(ValueError):
                self.check(self.text.replace(self.header,self.header+'\n\t\ttval: '+value))

    def test_mtval_read_or_store_corruption(self):
        for pc,field in ((0x8000202c,'rd_wdata'),(0x80002030,'mem_wdata')):
            rows=copy.deepcopy(self.rows)
            row=next(r for r in rows if r['event']=='retire' and int(r['pc'],16)==pc)
            row[field]='0000000000000001'
            with self.assertRaisesRegex(ValueError,'mtval CSR read'):self.check(rows=rows)

    def test_missing_handler_ledger_write(self):
        rows=copy.deepcopy(self.rows)
        row=next(r for r in rows if r['event']=='retire' and int(r['pc'],16)==0x80002030)
        row['mem_wmask']='00'
        with self.assertRaisesRegex(ValueError,'mtval CSR read'):self.check(rows=rows)

    def test_extra_fof_rvfi_trap(self):
        rows=copy.deepcopy(self.rows)
        row=next(r for r in rows if r['event']=='retire' and int(r['pc'],16)==0x8000213c)
        row['trap']='1'
        with self.assertRaisesRegex(ValueError,'Exactly one scalar S ECALL'):self.check(rows=rows)

    def test_tracer_privilege_not_skipped(self):
        with self.assertRaisesRegex(ValueError,'privilege differential'):
            self.check(self.text.replace(' S 00000000800021c4',' M 00000000800021c4'))

    def test_complete_real_capture(self):
        result=checker.audit(CASE)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['footprint']['checks'],2294)
        self.assertEqual(result['footprint']['failures'],0)
        self.assertEqual(result['native']['defined_compared_bytes'],684)
        self.assertEqual(result['lifecycle']['requests'],38)
        self.assertFalse(result['coverage_admitted'])


if __name__=='__main__':unittest.main()
