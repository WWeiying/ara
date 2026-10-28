from pathlib import Path
import unittest
from token_major import token_major

ROOT=Path(__file__).resolve().parents[4]


class PermutationTest(unittest.TestCase):
    def test_coordinates(self):
        self.assertEqual(token_major(bytes(range(12)),2,2,3),bytes([0,1,6,7,2,3,8,9,4,5,10,11]))

    def test_reject(self):
        for row,heads,tokens in [(0,8,256),(True,8,256),(2,0,3),(2,2,-1),(2,2,3)]:
            with self.subTest(shape=(row,heads,tokens)),self.assertRaises(ValueError):
                token_major(b'',row,heads,tokens)

    def test_real_capture_rows(self):
        for kind,row in [('q4_0',72),('q8_0',136)]:
            data=ROOT/'verification/out/quant-prefill-capture-20261028-01'/kind/'prefill/block'
            for name,width in [('attn_k_input-0.bin',row),('attn_v_input-0.bin',136)]:
                original=(data/name).read_bytes();permuted=token_major(original,width)
                for h in range(8):
                    for t in range(256):
                        self.assertEqual(permuted[(t*8+h)*width:(t*8+h+1)*width],
                                         original[(h*256+t)*width:(h*256+t+1)*width])
                self.assertEqual((data/name).read_bytes(),original)


if __name__=='__main__':unittest.main()
