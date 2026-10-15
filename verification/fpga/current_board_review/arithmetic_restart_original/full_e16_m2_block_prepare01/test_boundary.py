import unittest
from raw_boundary import BOOT,RawBoundary

class BoundaryTests(unittest.TestCase):
    def state(self,complete=True):
        s=RawBoundary()
        for pc,insn,rest in BOOT:self.assertEqual(s.enter(pc,insn,rest),'boot')
        self.assertEqual(s.enter(0x80000000,0x0004a197,''),'firmware')
        if complete:s.success(0x8000007a,0x00a2b023,1)
        return s
    def test_completed_trace_only_park_then_eof(self):
        s=self.state()
        self.assertEqual(s.enter(0x8000007e,0xa001,''),'park');s.finish()
        self.assertEqual(s.park,1)
    def test_completed_trace_helper_rejected(self):
        with self.assertRaisesRegex(ValueError,'Post-HTIF'):self.state().enter(0x80000c3a,0x7772d7,'')
    def test_completed_trace_side_effects_rejected(self):
        for rest in (' x5 0x0',' mem 0x80000000 0x1',' v24 0x0',' c8_vstart 0x0'):
            with self.subTest(rest=rest),self.assertRaisesRegex(ValueError,'Post-HTIF'):self.state().enter(0x8000007e,0xa001,rest)
    def test_completed_trace_wrong_code_rejected(self):
        with self.assertRaisesRegex(ValueError,'Post-HTIF'):self.state().enter(0x8000007e,0x13,'')
    def test_nonzero_or_wrong_htif_rejected(self):
        for args in ((0x8000007a,0x00a2b023,3),(0x8000007e,0x00a2b023,1)):
            with self.assertRaises(ValueError):self.state(False).success(*args)
    def test_partial_boot_or_completion_rejected(self):
        with self.assertRaises(ValueError):RawBoundary().enter(0x80000000,0x0004a197,'')
        with self.assertRaises(ValueError):self.state(False).finish()
    def test_boot_drift_reentry_rejected(self):
        pc,insn,rest=BOOT[0]
        with self.assertRaises(ValueError):RawBoundary().enter(pc,insn^1,rest)
        with self.assertRaises(ValueError):self.state().enter(pc,insn,rest)

if __name__=='__main__':unittest.main(verbosity=2)
