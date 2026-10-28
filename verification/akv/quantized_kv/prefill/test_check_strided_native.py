import unittest
from check_strided_native import LAYOUT,check_strided_log
from check_full_native import SCOPE
from test_check_native import fixture


class StridedCheckTest(unittest.TestCase):
    def test_complete_and_mutations(self):
        text,gold=fixture();text=SCOPE+'\n'+LAYOUT+'\n'+text
        for i,p,n in [(0,4,74),(1,1,20),(2,1,20),(3,4,74)]:
            marker=f'PREFILL_RESULT trial={i}'
            text=text.replace(marker,f'PREFILL_PANEL trial={i} panels={p} key_bytes={n*72}\n'+marker)
        result=check_strided_log(text,gold,1)
        self.assertTrue(result['token_major'])
        for old,new in [(LAYOUT,''),('panels=4','panels=1'),('key_bytes=5328','key_bytes=0'),
                        ('physical_kv_heads=8','physical_kv_heads=1'),('commands=4','commands=0')]:
            with self.subTest(old=old),self.assertRaises((AssertionError,ValueError)):
                check_strided_log(text.replace(old,new,1),gold,1)


if __name__=='__main__':unittest.main()
