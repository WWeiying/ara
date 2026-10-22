import unittest
import scoped_rv64c_memory as m


class Decode(unittest.TestCase):
    def test_actual_words(self):
        expected = {0xe422:('write',8,2,8,8),0xc190:('write',4,11,12,0),
                    0xc19c:('write',4,11,15,0),0x419c:('read',4,11,15,0),
                    0x4200:('read',4,12,8,0),0x610c:('read',8,10,11,0),
                    0x650c:('read',8,10,11,8),0x6908:('read',8,10,10,16),
                    0x6422:('read',8,2,8,8)}
        for word,fields in expected.items():
            d = m.decode(word)
            self.assertEqual(tuple(d[k] for k in ('kind','size','base','register','offset')),fields)

    def test_all_integer_formats_immediate_bits(self):
        # Independent format encoders exercise every legal unsigned immediate.
        for q in (0,2):
            for write in (False,True):
                for size in (4,8):
                    limit = (128 if size == 4 else 256) if q == 0 else (256 if size == 4 else 512)
                    for offset in range(0,limit,size):
                        f = (6 if size == 4 else 7) if write else (2 if size == 4 else 3)
                        word = f<<13|q
                        if q == 0:
                            word |= 3<<7|5<<2
                            word |= (offset>>3&7)<<10
                            word |= ((offset>>6&1)<<5 | (offset>>2&1)<<6) if size == 4 else (offset>>6&3)<<5
                            base,reg = 11,13
                        else:
                            base,reg = 2,13
                            if write:
                                word |= reg<<2
                                word |= ((offset>>2&15)<<9 | (offset>>6&3)<<7) if size == 4 else \
                                        ((offset>>3&7)<<10 | (offset>>6&7)<<7)
                            else:
                                word |= reg<<7|(offset>>5&1)<<12
                                word |= ((offset>>2&7)<<4 | (offset>>6&3)<<2) if size == 4 else \
                                        ((offset>>3&3)<<5 | (offset>>6&7)<<2)
                        d = m.decode(word)
                        self.assertEqual((d['size'],d['base'],d['register'],d['offset']),(size,base,reg,offset))
                        expanded = d['expanded']
                        self.assertEqual((expanded>>15)&31,base)
                        if write:
                            self.assertEqual((expanded>>20)&31,reg)
                            self.assertEqual((expanded>>25)<<5 | (expanded>>7)&31,offset)
                        else:
                            self.assertEqual((expanded>>7)&31,reg)
                            self.assertEqual(expanded>>20,offset)

    def test_reserved_unsupported_and_upper_bits(self):
        for word in (0x4002,0x6002,0x10000|0xc190):
            with self.assertRaises(ValueError):
                m.decode(word)
        for word in (0x2000,0xa000,0x0001,0x00000013):
            self.assertIsNone(m.decode(word))


if __name__ == '__main__':
    unittest.main()
