import unittest
import preflight_c910_float_edge776 as pre


class FloatEdges(unittest.TestCase):
    def test_overflow_rne_rtz(self):
        for width, infinity, maximum in [(16, 0x7c00, 0x7bff), (32, 0x7f800000, 0x7f7fffff), (64, 0x7ff0000000000000, 0x7fefffffffffffff)]:
            self.assertEqual(pre.gold(width, 2, 0)[2:], (infinity, 5))
            self.assertEqual(pre.gold(width, 2, 1)[2:], (maximum, 5))
    def test_negative_tiny_sign_and_flags(self):
        for width in (16, 32, 64):
            for rm in (0, 1): self.assertEqual(pre.gold(width, 6, rm)[2:], (1 << (width - 1), 3))
    def test_exact_subnormal_no_flags(self):
        for width, expected in [(16, 0x200), (32, 0x400000), (64, 0x8000000000000)]:
            self.assertEqual(pre.gold(width, 4, 0)[2:], (expected, 0))
    def test_recovery(self): self.assertEqual(pre.gold(32, 7, 0)[2:], (0x3f400000, 0))
    def test_matrix_bounds_rejected(self):
        for args in [(8, 0, 0), (16, 8, 0), (32, 0, 2)]:
            with self.assertRaises(ValueError): pre.gold(*args)
    def test_packing(self):
        self.assertEqual(pre.word(0x7bff, 16), 0x7bff7bff7bff7bff)
        with self.assertRaises(ValueError): pre.word(0x10000, 16)
    def test_actual_vse_element_widths(self):
        self.assertEqual(pre.vector_store_bytes(0x3800, 16), b'\x00\x38')
        self.assertEqual(pre.vector_store_bytes(0x3f000000, 32), b'\x00\x00\x00\x3f')
        self.assertEqual(pre.vector_store_bytes(0x3fe0000000000000, 64), b'\x00\x00\x00\x00\x00\x00\xe0\x3f')
        with self.assertRaises(ValueError): pre.vector_store_bytes(0x10000, 16)
    def test_implicit_vector_rejected(self):
        with self.assertRaises(ValueError): pre.linked('  80002000: 02000057 vadd.vv v0,v0,v0')
    def test_no_trap_shortcut(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'trace'; path.write_text('exception trap\n')
            with self.assertRaises(ValueError): pre.validate(path, {'trap_fail': 0})


if __name__ == '__main__': unittest.main()
