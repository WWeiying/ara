import unittest
from value_cache_check import check_log


def fixture():
    lines=['VCACHE_CAP q4=1 rows=16 d=128 first_query=0 tokens=8 trials=4',
        'VCACHE_SCOPE whole_call=1 admission=1 scatter=1 baseline=grouped_qbs',
        'VCACHE_LAYOUT token_major=1 physical_kv_heads=8 selected_head=0']
    for i,mode in enumerate((0,1,1,0)):
        lines += [f'VCACHE_BEGIN trial={i} shared={mode}',f'VCACHE_PANEL trial={i} panels=2 key_bytes=864',
            f'VCACHE_RESULT trial={i} shared={mode} cycles=100 commands=8 values={8 if mode else 12} fcsr=8 vcsr=5 errors=0 hex='+('00000000'*2048)]
    return '\n'.join(lines+['VCACHE_SUITE_PASS'])


class Check(unittest.TestCase):
    def test_good(self):
        self.assertEqual(check_log(fixture(),bytes(163840),1)['speedup'],1)

    def test_reject_mutations(self):
        for old,new in [('values=8','values=12'),('commands=8','commands=4'),
                        ('fcsr=8','fcsr=0'),('vcsr=5','vcsr=0'),('errors=0','errors=1'),
                        ('key_bytes=864','key_bytes=865'),('VCACHE_SUITE_PASS',''),
                        ('hex=00000000','hex=3f800000'),('first_query=0','first_query=16')]:
            with self.subTest(old=old):
                with self.assertRaises(ValueError):check_log(fixture().replace(old,new,1),bytes(163840),1)


if __name__=='__main__':unittest.main()
