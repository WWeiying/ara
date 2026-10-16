import unittest
from audit_segment_setup import inspect


OUTPUT = '''unhandled signal 7 code 0x1
epc : 000000000001059c
a0 : 00000000000150c1 a1 : 00000000000130c1
a3 : 0000000000000000 a4 : 0000000000000040
t0 : 0000000000000040 a6 : 00000000000130c1
badaddr: 00000000000130c1 cause: 0000000000000004
'''
DIS = '''10592: 008772d7 vsetvli t0,a4,e16,m1,tu,mu
10596: 00171313 slli t1,a4,0x1
1059a: 882e mv a6,a1
1059c: 02085c07 vle16.v v24,(a6)
105b6: 40055c07 vlseg3e16.v v24,(a0),v0.t
'''


class SegmentSetupTests(unittest.TestCase):
    def check(self, output=OUTPUT, dis=DIS):
        return inspect(dict(name='rvv_segments_misaligned_e16_m1', sew=16, lmul='m1', sha256='elf'),
                       dict(status='failed', output=output), dis)

    def test_preparation_not_target(self):
        row = self.check()
        self.assertEqual(row['preparation_vl'], 64)
        self.assertEqual(row['target_vl_argument'], 0)
        self.assertFalse(row['architectural_bug_proven'])
        self.assertFalse(row['reduced_board_reproduction_confirmed'])

    def test_other_traps_or_truncated_evidence_rejected(self):
        for output in (OUTPUT.replace('signal 7', 'signal 11'),
                       OUTPUT.replace('cause: 0000000000000004', 'cause: 000000000000000d'),
                       OUTPUT.replace('1059c', '105b6'),
                       OUTPUT.replace('130c1', '130c0'),
                       OUTPUT.replace('a3 : 0000000000000000', 'a3 : 0000000000000001'),
                       OUTPUT.replace('a6 : 00000000000130c1', ''), OUTPUT + OUTPUT):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):self.check(output)

    def test_different_instruction_or_prelude_rejected(self):
        for dis in (DIS.replace('vle16.v', 'vle32.v'), DIS.replace('mv a6,a1', 'mv a6,a0'),
                    DIS.replace('e16,m1', 'e16,m2'), DIS.replace('vlseg3e16.v', 'vlseg4e16.v')):
            with self.assertRaises(ValueError):self.check(dis=dis)


if __name__ == '__main__':
    unittest.main()
