import unittest
from analyze_trace import analyze


def fixture():
    lines=[]
    for i,candidate in enumerate((0,1,1,0)):
        lines += [f'REGISTER_PV_BEGIN trial={i} candidate={candidate}',
            f'[ARA_CONTRACT_TRACE] cycle={i+1} req=1/1 fire=1 id=0 insn=00007057 errors=0000000',
            f'REGISTER_PV_RESULT trial={i} candidate={candidate} errors=0']
    return lines


class TraceTest(unittest.TestCase):
    def test_positive(self):
        result=analyze(fixture(),100)
        self.assertEqual(result['baseline'],{'vset':1})
        self.assertEqual(result['candidate'],{'vset':1})
        self.assertFalse(result['memory_bytes_measured'])

    def test_invalid(self):
        with self.assertRaises(ValueError):analyze(fixture(),4)
        with self.assertRaises(ValueError):analyze(fixture()[:-1],100)
        for old,new in [('cycle=2','cycle=1'),('errors=0000000','errors=0000001'),
                        ('trial=1 candidate=1','trial=1 candidate=0'),
                        ('cycle=2 req=1/1 fire=1 id=0 insn=00007057',
                         'cycle=2 req=1/1 fire=1 id=0 insn=00000007')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                analyze('\n'.join(fixture()).replace(old,new,1).splitlines(),100)


if __name__=='__main__':unittest.main()
