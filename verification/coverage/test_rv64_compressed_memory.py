"""RV64 encodings and exact immediates, including FP register zero."""
import unittest
import rv64_compressed_memory as m


class Decode(unittest.TestCase):
    def test_actual_fldsp_encodings(self):
        for word,reg,offset in ((0x3406,8,96),(0x24e6,9,88)):
            self.assertEqual(m.decode(word),dict(kind='read',size=8,floating=True,register=reg,
                base_register=2,offset=offset,mnemonic='C.FLDSP'))

    def test_all_memory_arms_rv64_not_rv32_flw(self):
        for quadrant in (0,2):
            for funct3,size,fp,load in ((1,8,True,True),(2,4,False,True),(3,8,False,True),
                                      (5,8,True,False),(6,4,False,False),(7,8,False,False)):
                word = (funct3<<13)|quadrant|(9<<7)|(3<<2)
                d = m.decode(word)
                self.assertEqual((d['size'],d['floating'],d['kind']),(size,fp,'read' if load else 'write'))

    def test_every_ld_immediate_bit(self):
        for q in (0,2):
            bits = {10:3,11:4,12:5,5:6,6:7} if q==0 else {5:3,6:4,12:5,2:6,3:7,4:8}
            base = 0x2000|q|(1<<7 if q==2 else 0)
            for insn_bit,address_bit in bits.items():
                self.assertEqual(m.decode(base|(1<<insn_bit))['offset'],1<<address_bit)

    def test_every_sdsp_immediate_bit(self):
        for insn_bit,address_bit in {10:3,11:4,12:5,7:6,8:7,9:8}.items():
            self.assertEqual(m.decode(0xa002|(1<<insn_bit))['offset'],1<<address_bit)

    def test_fp_zero_valid_integer_sp_zero_reserved(self):
        self.assertEqual(m.decode(0x2002)['register'],0)
        self.assertTrue(m.decode(0x2002)['floating'])
        self.assertIsNone(m.decode(0x4002)); self.assertIsNone(m.decode(0x6002))

    def test_non_memory_or_invalid_word(self):
        self.assertIsNone(m.decode(0x0001)); self.assertIsNone(m.decode(0x0003))
        for word in (-1,0x10000,'3406'):
            with self.assertRaises(ValueError): m.decode(word)


if __name__=='__main__': unittest.main()
