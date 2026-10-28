import struct
import unittest
from check_native import check_log


def fixture():
    lines=['PREFILL_CAP q4=1 rows=8 d=128 first_query=16 tokens=20 trials=4']
    for trial,shared in enumerate((0,1,1,0)):
        lines.append(f'PREFILL_BEGIN trial={trial} shared={shared}')
        lines.append(f'PREFILL_RESULT trial={trial} shared={shared} cycles={100 if not shared else 90} '
                     f'commands=4 values={20 if shared else 74} fcsr=1 vcsr=5 errors=0 hex='+'3f800000'*1024)
    lines.append('PREFILL_SUITE_PASS')
    return '\n'.join(lines),struct.pack('<40960f',*([1.]*40960))


class CheckerTest(unittest.TestCase):
    def test_positive(self):
        text,golden=fixture()
        result=check_log(text,golden,1)
        self.assertEqual(result['baseline_cycles'],100)
        self.assertEqual(result['shared_cycles'],90)

    def test_mutations(self):
        text,golden=fixture()
        for old,new in [('PREFILL_SUITE_PASS',''),('commands=4','commands=0'),
                        ('values=20','values=74'),('errors=0','errors=1'),
                        ('cycles=100','cycles=0'),('fcsr=1','fcsr=32'),
                        ('vcsr=5','vcsr=0'),('3f800000','7fc00000'),
                        ('PREFILL_BEGIN trial=0 shared=0','PREFILL_BEGIN trial=1 shared=0')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_log(text.replace(old,new,1),golden,1)
        with self.assertRaises(ValueError): check_log(text,golden,0)
        with self.assertRaises(ValueError): check_log(text,golden[:-4],1)
        with self.assertRaises(ValueError): check_log(text,bytes(len(golden)),1)
        # Later-trial bit changes within the numerical tolerance still fail exact pairing.
        marker='PREFILL_RESULT trial=1'
        first,second=text.split(marker,1)
        with self.assertRaises(ValueError):
            check_log(first+marker+second.replace('3f800000','3f800001',1),golden,1)


if __name__=='__main__': unittest.main()
