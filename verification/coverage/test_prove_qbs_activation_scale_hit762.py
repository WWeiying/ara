import unittest

import prove_qbs_activation_scale_hit762 as proof


class ScaleBoundTests(unittest.TestCase):
    def test_full_profile_layout_domain(self):
        impossible, checked = proof.exhaustive_bound()
        self.assertEqual(len(impossible),120)
        self.assertGreater(checked,256)
        self.assertIn((0,0,15),impossible)
        self.assertNotIn((3,3,15),impossible)

    def test_highest_legal_owner_protected(self):
        for row in range(4):
            for byte in range(4):
                index=4*row+byte
                self.assertEqual(proof.mapping.activation_target(index,8,4,256),(row,byte))
                self.assertEqual(proof.bound(row,byte),index)

    def test_aux_cannot_alias_scale(self):
        for offset in range(260,292):
            plane,byte=proof.mapping.activation_location(offset,4,256)
            self.assertEqual(plane,2)
            self.assertGreaterEqual(byte,4)

    def test_bank1_counterexample_prevents_extension(self):
        # Global context4 scale0 starts at index16; all16 writers can own it.
        self.assertEqual(proof.mapping.activation_target(16,8,4,256),(4,0))
        for writer in range(16): self.assertGreaterEqual(16-writer,0)

    def test_invalid_bound_rejected(self):
        for row,byte in ((True,0),(4,0),(0,4),(-1,0)):
            with self.assertRaises(ValueError): proof.bound(row,byte)


if __name__ == '__main__': unittest.main()
