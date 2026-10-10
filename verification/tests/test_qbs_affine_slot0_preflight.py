import struct
import unittest
import build_qbs_affine_slot0_preflight as m


class AffineFixtureTests(unittest.TestCase):
    def test_native_sizes_and_nonzero_affine(self):
        for phase in (0, 1):
            w, a, gold = m.fixture(phase)
            self.assertEqual((len(w), len(a), len(gold)), (1280, 2496, 64))
            for row in range(8):
                base = 64+144*row
                self.assertEqual(struct.unpack_from('<e', w, base)[0], row+1+phase)
                self.assertEqual(struct.unpack_from('<e', w, base+2)[0], row+2-phase)
                self.assertEqual(w[base+4:base+12], bytes([1]*8))
                self.assertEqual(w[base+12:base+16], bytes([0x11]*4))

    def test_gold_independent_closed_form(self):
        for phase in (0, 1):
            _, _, gold = m.fixture(phase)
            for c in range(8):
                for r in range(8):
                    actual = struct.unpack('<f', struct.pack('<I', gold[8*c+r]))[0]
                    self.assertEqual(actual, (256*r if phase == 0 else 512*r+1280)*(c+1))

    def test_activation_bsums_interleaving(self):
        _, a, _ = m.fixture(0)
        for c in range(8):
            self.assertEqual(struct.unpack_from('<f', a, 68+4*c)[0], c+1)
            self.assertEqual([a[100+8*i+c] for i in range(256)], [1]*256)
            for g in range(16):
                self.assertEqual(struct.unpack_from('<h', a, 2148+16*g+2*c)[0], 16)

    def test_invalid_phase(self):
        for phase in (True, -1, 2):
            with self.assertRaises(ValueError): m.fixture(phase)

    def test_precise_template_edits(self):
        body, asm = m.templates()
        self.assertIn('c->weight_profile == QBS_WEIGHT_PROFILE_Q4_K', body)
        self.assertIn('source_bytes == 7840', body)
        self.assertIn('MATRIX_EXEC 0, 8, 0x0eb5045b', asm)
        self.assertIn('MATRIX_EXEC 1, 8, 0x0eb5045b', asm)
        self.assertIn('complete initial VRF source image', body)
        self.assertIn('all descriptor/source guards', body)

    def test_template_ambiguity_rejected(self):
        with self.assertRaises(ValueError): m.replace_one('x x', 'x', 'y')


if __name__ == '__main__': unittest.main()
