import unittest
from check_soc import check


def log():
    return '\n'.join(
        f'DECODE_SUMS k={k} trial={t} candidate={int(t in (1,2))} cycles=100 fcsr=1 vcsr=5 digest=0123456789abcdef'
        for k in (1536,8960) for t in range(4))+'\nDECODE_SUMS_RESULT errors=0 trials=8\n'


class CheckerTest(unittest.TestCase):
    def test_good(self):
        rows=check(log())
        self.assertEqual(len(rows),8)
        self.assertEqual(check(log().replace('cycles=100','cycles=200'),rows)[0]['cycles'],200)

    def test_reject(self):
        for text in (log().replace('errors=0','errors=1'),log()+log(),
                     log().replace('cycles=100','cycles=0',1),
                     log().replace('trial=0','trial=1',1),
                     log().replace('fcsr=1','fcsr=2',1),
                     log().replace('0123456789abcdef','1123456789abcdef',1)):
            with self.subTest(text=text),self.assertRaises(ValueError): check(text)

    def test_golden(self):
        with self.assertRaises(ValueError):
            check(log().replace('0123456789abcdef','1123456789abcdef'),check(log()))


if __name__=='__main__': unittest.main()
