import io
import unittest
from decode_pc_profile import check_output,profile

SYMBOLS='1000 100 T main\n1010 T decode_profile_begin\n1040 T decode_profile_end\n2000 100 t work\n'


def trace():
    header='cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'
    records=[(10,0,0x1010,0xc0002573,100),(12,1,0x2000,0x13,0),
             (22,2,0x2004,0x13,0),(30,3,0x1040,0xc0002573,120)]
    return '\n'.join([header]+[f'{c},retire,{o},0,-1,{pc:016x},{i:08x},10,{v:016x},0,00,00,0,0'
                                     for c,o,pc,i,v in records])


class ProfileTest(unittest.TestCase):
    def test_accounting(self):
        p=profile(io.StringIO(trace()),SYMBOLS,20)
        self.assertEqual(p['retired_instructions'],3)
        self.assertEqual(p['retirement_span_cycles'],20)
        self.assertEqual(p['functions'][0]['function'],'work')
        self.assertEqual(p['functions'][0]['gap_cycles'],12)

    def test_mutations(self):
        for old,new in [('0000000000002004','0000000000004004'),
                        ('30,retire,3','30,retire,1'),('22,retire,2','9,retire,2'),
                        ('0000000000000078','0000000000000079'),
                        ('0000000000001040','0000000000001044'),
                        ('c0002573','00000013')]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                profile(io.StringIO(trace().replace(old,new)),SYMBOLS,20)

    def test_output(self):
        text='DECODE_PROFILE_SCOPE query=19 heads=2 dim=128 visible=20 token_major=1 q4=1\n'+\
             'DECODE_PROFILE_RESULT cycles=20 commands=1 groups=1 values=20 panels=1 key_bytes=1440 fcsr=1 vcsr=5 errors=0 hex='+\
             '00000000'*256+'\nDECODE_PROFILE_PASS\n'
        self.assertEqual(check_output(text,bytes(163840),1)['outputs'],256)
        for old,new in [('commands=1','commands=0'),('errors=0','errors=1'),
                        ('DECODE_PROFILE_PASS',''),('vcsr=5','vcsr=0'),
                        ('00000000'*256,'7fc00000'+'00000000'*255)]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_output(text.replace(old,new),bytes(163840),1)


if __name__=='__main__':unittest.main()
