import struct
import unittest
from check_selector_native import check_log


def fixture(q4=1):
    lines=['SELECTOR_SCOPE whole_call=1 query=19 heads=2 dim=128 visible=20 token_major=1 trials=4',
           f'SELECTOR_FORMAT q4={q4}']
    for trial,aligned in enumerate((0,1,1,0)):
        lines.extend([f'SELECTOR_BEGIN trial={trial} aligned={aligned}',
          f'SELECTOR_RESULT trial={trial} aligned={aligned} cycles={100 if aligned else 200} '+
          f'commands=1 groups=1 values=20 panels=1 key_bytes={1440 if q4 else 2720} '+
          'fcsr=1 vcsr=5 errors=0 hex='+'00000000'*256])
    return '\n'.join(lines+['SELECTOR_SUITE_PASS'])


class SelectorCheck(unittest.TestCase):
    def test_positive(self):
        for q4 in (0,1):
            self.assertEqual(check_log(fixture(q4),bytes(163840),q4)['speedup'],2.)

    def test_explicit_candidate_field(self):
        text=fixture().replace('aligned=','candidate=')
        self.assertEqual(check_log(text,bytes(163840),1,mode_field='candidate')['trials'][1]['candidate'],1)
        with self.assertRaises(ValueError):check_log(text,bytes(163840),1)
        with self.assertRaises(ValueError):check_log(fixture(),bytes(163840),1,mode_field='candidate')

    def test_mutations(self):
        text=fixture()
        for old,new in [('commands=1','commands=0'),('groups=1','groups=0'),
            ('values=20','values=19'),('panels=1','panels=0'),('key_bytes=1440','key_bytes=0'),
            ('vcsr=5','vcsr=0'),('errors=0','errors=1'),('cycles=200','cycles=0'),
            ('SELECTOR_BEGIN trial=0 aligned=0','SELECTOR_BEGIN trial=0 aligned=1'),
            ('SELECTOR_SUITE_PASS',''),('00000000'*256,'7fc00000'+'00000000'*255)]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_log(text.replace(old,new,1),bytes(163840),1)
        with self.assertRaises(ValueError):check_log(text.replace('fcsr=1','fcsr=0',1),bytes(163840),1)
        golden=bytearray(163840)
        struct.pack_into('<f',golden,19*16*128*4,1.)
        with self.assertRaises(ValueError):check_log(text,golden,1)
        with self.assertRaises(ValueError):check_log(text+'\nSELECTOR_SUITE_PASS',bytes(163840),1)
        with self.assertRaises(ValueError):check_log(text,bytes(163840),0)


if __name__=='__main__':unittest.main()
