"""Actual terminal metadata adapter negatives, no raw parse."""
from copy import deepcopy
import unittest
import checker as c
import terminal_gate as t
class TerminalTests(unittest.TestCase):
    def actual(self):
        root=c.REF/'reference01'
        return [c.read(t.REPORT),c.read(c.REF/'READY.json'),c.read(root/'result.json'),
            c.read(root/'execution.json'),c.read(root/'audit_execution.json'),c.read(root/'preflight_pins.json')]
    def test_actual_terminal_report(self):
        t.verify(c.read(c.HERE/'reference_terminal_binding.json'),c.read(c.REF/'READY.json'))
    def test_wrong_identity_numeric_counts_eof_scope(self):
        for path,value in ((('accepted',),False),(('READY_sha256',),'wrong'),(('entry_sha256',),'wrong'),
            (('result_sha256',),'wrong'),(('pin_drift',),['drift']),
            (('actual_reference_wait','returncode'),17),(('actual_audit_wait','returncode'),17),
            (('actual_reference_wait','elapsed_s'),0),(('actual_audit_wait','timed_out'),True),
            (('scope','packed_reads'),36854),(('scope','results'),131039),
            (('counts','EOF_checked'),False),(('counts','whole_raw'),1),(('DUT_acceptance',),True)):
            args=self.actual();where=args[0]
            for name in path[:-1]:where=where[name]
            where[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(ValueError):t.validate(*args)
if __name__=='__main__':unittest.main(verbosity=2)
