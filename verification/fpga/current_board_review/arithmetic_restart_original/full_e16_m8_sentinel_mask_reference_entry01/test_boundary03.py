"""Short parser boundaries only; no full Host or raw reference reparse."""
import unittest
from context import *
from reference_check02 import parse_record
class Boundary(unittest.TestCase):
    def test_blank(self):
        for line in ('','\n',' \t\n'):self.assertIsNone(parse_record(line))
    def test_actual_park_record(self):
        p=read(HERE/'PROFILE02.json')
        m=parse_record('core   0: 3 0x%016x (0x%08x)\n'%(p['park_pc'],p['park_insn']))
        park_gate(int(m[1],16),int(m[2],16),m[3],p)
    def test_nonempty_malformed_before_or_after_HTIF(self):
        for phase in ('pre_HTIF','post_HTIF'):
            for line in ('garbage\n','core 0: broken\n','core 1: 3 0x8000007e (0x0000a001)\n'):
                with self.subTest(phase=phase,line=line):
                    with self.assertRaises(ValueError):parse_record(line)
    def test_late_effect(self):
        p=read(HERE/'PROFILE02.json')
        m=parse_record('core 0: 3 0x%016x (0x%08x) x1 0x01'%(p['park_pc'],p['park_insn']))
        with self.assertRaises(ValueError):park_gate(int(m[1],16),int(m[2],16),m[3],p)
    def test_HTIF_cost_basis(self):
        text=(HERE/'reference02.py').read_text()
        self.assertIn("within=report['firmware_to_HTIF']<=3000000",text)
        self.assertIn("firmware=report['firmware_to_HTIF']",text)
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Boundary))
    save(HERE/'HOST03.json',dict(status='PASS_SHORT_PARSER_BOUNDARIES' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),raw_reads=0,reference_runs=0))
    raise SystemExit(not result.wasSuccessful())
