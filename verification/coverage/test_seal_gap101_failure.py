import unittest
import seal_gap101_failure as m


class StoreTests(unittest.TestCase):
    def test_right_justified_word_upper_mask(self):
        r = dict(insn="0000c1d4", mem_addr="0000000080005784", mem_wmask="f0", mem_wdata="0000000000000433")
        self.assertEqual(m.scalar_store(r), (0x80005784, bytes.fromhex("33040000")))

    def test_bad_mask_rejected(self):
        r = dict(insn="0000c1d4", mem_addr="0000000080005784", mem_wmask="0f", mem_wdata="0000000000000433")
        with self.assertRaises(ValueError): m.scalar_store(r)

    def test_full_word(self):
        r = dict(insn="0000e970", mem_addr="0000000080005890", mem_wmask="ff", mem_wdata="a5a5a5a5a5a5405f")
        self.assertEqual(m.scalar_store(r), (0x80005890, bytes.fromhex("5f40a5a5a5a5a5a5")))


if __name__ == "__main__": unittest.main()
