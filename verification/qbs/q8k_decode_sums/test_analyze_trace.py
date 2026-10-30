import unittest
from analyze_trace import analyze


def sample():
    return b'''cycle,event,arch_seq,vid,insn,vl,eew,be
1,alloc,10,0,12345678,64,1,00
2,write,10,0,12345678,64,1,ff
3,done,10,0,12345678,64,1,00
4,alloc,10,0,12345678,16,1,00
5,write,10,0,12345678,16,1,03
6,done,10,0,12345678,16,1,00
7,alloc,11,0,12345678,16,1,00
9,done,11,0,12345678,16,1,00
'''


class TraceTest(unittest.TestCase):
    def test_multiple_uops(self):
        group=analyze(sample(),{'12345678':('reduce',2)})['reduce']
        self.assertEqual(group['architectural_count'],2)
        self.assertEqual(group['backend_uops'],3)
        self.assertEqual(group['architectural_residence_mean'],3.5)
        self.assertEqual(group['enabled_write_bytes'],10)

    def test_reject_incomplete_and_overlap(self):
        for raw in (sample().replace(b'9,done,11,0,12345678,16,1,00\n',b''),
                    sample().replace(b'3,done,10,0,12345678,64,1,00\n',b'')):
            with self.assertRaises(ValueError): analyze(raw,{'12345678':('reduce',2)})


if __name__=='__main__': unittest.main()
