import unittest
from check_projection_pair import check


def sample():
    return '\n'.join([
        f'DECODE_PROJECTION trial={i} candidate={int(i in (1,2))} prep=10 execute=20 total=30 fcsr=1 vcsr=3 digest=0123456789abcdef'
        for i in range(4)]+['DECODE_PROJECTION_RESULT errors=0 trials=4 m=1 n=1536 k=1536 commands=192'])


class ProjectionPairTest(unittest.TestCase):
    def test_valid(self):
        rows=check(sample())
        self.assertEqual(check(sample(),rows),rows)

    def test_reject_bad_cycles_errors_and_digest(self):
        for text in (sample().replace('total=30','total=29',1),
                     sample().replace('errors=0','errors=1'),
                     sample().replace('0123456789abcdef','0123456789abcdee',1)):
            with self.assertRaises(ValueError): check(text)

    def test_golden_mismatch(self):
        golden=check(sample())
        golden[0]['fcsr']=0
        with self.assertRaises(ValueError): check(sample(),golden)


if __name__=='__main__': unittest.main()
