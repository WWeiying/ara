import unittest
from check_context_qkv import check


def fixture():
    return '\n'.join(
        f'CONTEXT_QKV trial={i} reuse={int(i in (1,2))} prep=3 execute=3 total=10 fcsr=1 vcsr=3 digest=0123456789abcdef'
        for i in range(4))+'\nCONTEXT_QKV_RESULT errors=0 trials=4 k=1536 outputs=2048 commands=256\n'


class CheckTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(len(check(fixture(),check(fixture()))),4)

    def test_reject_failure(self):
        for old,new in (('errors=0','errors=1'),('trial=2 reuse=1','trial=2 reuse=0'),
                        ('total=10','total=5'),('commands=256','commands=128')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                check(fixture().replace(old,new,1))

    def test_reject_numerical_and_golden_drift(self):
        with self.assertRaises(ValueError):
            check(fixture().replace('digest=0123456789abcdef','digest=0123456789abcdee',1))
        with self.assertRaises(ValueError):
            check(fixture().replace('fcsr=1','fcsr=0'),check(fixture()))


if __name__=='__main__':unittest.main()
