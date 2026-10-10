import unittest
import check_narrow_source_group_preflight_v2 as p


class Tests(unittest.TestCase):
    def test_actual_objdump_word_and_byte_formats(self):
        self.assertEqual(p.rvv_words('80002134: 0022f057     \tvsetvli\n'
                                    '800021a0: 57 0c 9a ba  \t.word\n'),
                         [(0x80002134,0x0022f057),(0x800021a0,0xba9a0c57)])

    def test_compressed_scalar_and_data_excluded(self):
        self.assertEqual(p.rvv_words('80000000: 6299 \tlui\n80000004: 34202373 \tcsrr\n'),[])

    def test_missing_extra_wrong_word_and_wrong_PC_rejected(self):
        words=[0x0022f057,0x02050a07,0x02058c07,0x02058c27,0xc0247057,p.prior.FAULT,
               0x0022f057,0x02050c27,0xc0247057,0x0341bc57,0x0022f057,0x02058c27]
        pairs=list(enumerate(words));symbols=dict(ng_fault=5,ng_recovery=9)
        p.verify_words(pairs,symbols)
        for bad in (pairs[:-1],pairs+[(12,0x57)],pairs[:5]+[(5,0xb29a0c57)]+pairs[6:],
                    pairs[:5]+[(100,p.prior.FAULT)]+pairs[6:]):
            with self.assertRaises(ValueError):p.verify_words(bad,symbols)


if __name__=='__main__':unittest.main()
