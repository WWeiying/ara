import struct
import unittest
from check_native import check_log


def fixture(query,q4=1):
    n=query+1
    lines=[f'REGISTER_PV_SCOPE whole_call=1 query={query} heads=2 dim=128 visible={n} token_major=1 trials=4',
        f'REGISTER_PV_FORMAT q4={q4}',
        'REGISTER_PV_BINDINGS value=shared_rvv_q8_0 baseline=current_shared candidate=register_pv']
    for i,mode in enumerate((0,1,1,0)):
        lines.extend([f'REGISTER_PV_BEGIN trial={i} candidate={mode}',
            f'REGISTER_PV_RESULT trial={i} candidate={mode} cycles={100 if mode else 200} '+
            f'commands=1 groups=1 values={n} panels=1 key_bytes={n*(72 if q4 else 136)} '+
            'fcsr=1 vcsr=5 errors=0 hex='+'00000000'*256])
    return '\n'.join(lines+['REGISTER_PV_SUITE_PASS'])


class ContextCheck(unittest.TestCase):
    def test_positive(self):
        for query in (0,7,19):
            for q4 in (0,1):
                self.assertEqual(check_log(fixture(query,q4),bytes(163840),q4,query)['speedup'],2)

    def test_scope_and_golden(self):
        with self.assertRaises(ValueError):check_log(fixture(7),bytes(163840),1,19)
        gold=bytearray(163840);struct.pack_into('<f',gold,7*16*128*4,1)
        with self.assertRaises(ValueError):check_log(fixture(7),gold,1,7)
        for old,new in [('values=8','values=20'),('key_bytes=576','key_bytes=1440'),
                        ('commands=1','commands=0'),('candidate=register_pv','candidate=other'),
                        ('errors=0','errors=1'),('fcsr=1','fcsr=0')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_log(fixture(7).replace(old,new,1),bytes(163840),1,7)


if __name__=='__main__':unittest.main()
