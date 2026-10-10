import unittest

import review_qbs_bank1_group_hit789_all_cycle as c


class SourceDomain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.domain = c.domain()

    def test_exact_zero_geometry(self):
        self.assertEqual(sum(2*(32-len(v)) for v in self.domain.values()), 3232)
        self.assertEqual(sum(bool(set(range(32))-v) for v in self.domain.values()), 72)

    def test_quant_all_original_writer_indices(self):
        for row in range(4):
            for group in range(1, 16):
                self.assertEqual(self.domain[row, group],
                                 {16*s+b for s in (0, 1) for b in range(row, 16, 4)})

    def test_invalid_or_narrow_layout_never_bank1(self):
        for profile in ('Q8_K', 'Q8_0', 'INVALID'):
            for layout in ('ROW', 'M4'):
                for context in range(4):
                    for offset in (0, 4, 32, 256, 288, 4092):
                        for b in range(16):
                            self.assertIsNone(c.target(profile, layout, offset, b, context))

    def test_offset_alignment_is_necessary_not_relaxed(self):
        # An arbitrary/forced offset1 would destroy the residue invariant.
        # It is NOT a legal integrated producer and must not enter the proof.
        mapped = c.target('Q8_K', 'M8', 129, 3, 0)
        self.assertEqual(mapped, (0, 1))
        self.assertNotIn(3, self.domain[mapped])

    def test_inactive_other_slot_cannot_authorize_stale_target(self):
        self.assertFalse(c.qualified_hit(False, True, True, (1, 1), (1, 1)))
        self.assertFalse(c.qualified_hit(True, False, True, (1, 1), (1, 1)))
        self.assertFalse(c.qualified_hit(True, True, False, (1, 1), (1, 1)))
        self.assertTrue(c.qualified_hit(True, True, True, (1, 1), (1, 1)))

    def test_pending_preserves_byte_index_no_compaction(self):
        for members in self.domain.values():
            self.assertEqual({b+16 for b in members if b < 16}, {b for b in members if b >= 16})


if __name__ == '__main__':
    unittest.main()
