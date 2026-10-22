"""Host-only oracle tests; no claim of hardware execution."""
import unittest
import run_masklogical_same_source_repair as r


class MatrixOracleTests(unittest.TestCase):
    def test_complete_original_matrix(self):
        self.assertEqual(len(r.cases()), 68)
        self.assertEqual(sum(len(r.expected(c)) for c in r.cases()), 8224)
        self.assertEqual(sum(vl > start for _, vl, start, _ in r.cases()), 44)

    def test_byte_oracle_against_bit_definition(self):
        for case in r.cases():
            op, vl, start, mode = case
            for byte, value in r.expected(case).items():
                for bit in range(8):
                    index = byte * 8 + bit
                    want = ((0xa5 ^ byte * 7) >> bit) & 1
                    if start <= index < vl:
                        if mode != 1: want = int(op >= 2)
                        else:
                            a = ((0x69 ^ byte * 13) >> bit) & 1
                            b = ((0xc3 ^ byte * 29) >> bit) & 1
                            if op == 0: want = int(a != b)
                            elif op == 1: want = int(not a and b)
                            elif op == 2: want = int(a == b)
                            else: want = int(not a or b)
                    self.assertEqual((value >> bit) & 1, want)

    def test_distinct_negative_not_same_source_constant(self):
        for op in range(4):
            constant = 255 if op >= 2 else 0
            self.assertTrue(any(v != constant for v in r.expected((op, 1024, 0, 1)).values()))

    def test_empty_windows_preserve_every_byte(self):
        for op in range(4):
            for vl, start in ((0, 0), (31, 31), (31, 40)):
                self.assertEqual(r.expected((op, vl, start, 0)),
                                 {i: (0xa5 ^ i * 7) & 255 for i in range(128)})


if __name__ == '__main__':
    unittest.main()
