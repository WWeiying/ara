"""Geometry and independent-reference contracts for the queue supplement."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_rvv_queue_gap28 as gen


class QueueGap28Tests(unittest.TestCase):
    def test_generated_selection_and_distinct_sources(self):
        cases = gen.cases()
        self.assertEqual(len(cases), 36)
        selection = json.loads(Path(__file__).with_name("rvv_queue_gap28_selection.json").read_text())
        self.assertEqual(selection["tests"], ["rvv:" + c[0] for c in cases])
        self.assertEqual(len(set(selection["tests"])), 36)
        self.assertEqual([c[1] for c in cases[:3]], [0, 1, 2])
        sources = [gen.render(c) for c in cases]
        self.assertEqual(len({hashlib.sha256(s.encode()).hexdigest() for s in sources}), 36)
        for c, source in zip(cases, sources):
            self.assertEqual((gen.DEST / (c[0] + ".c")).read_text(), source)
        for kind in range(3):
            self.assertEqual(sum(c[1] == kind for c in cases), 12)

    def test_legal_groups_and_bounded_geometry(self):
        for _, kind, eew, lmul, _ in gen.cases():
            maximum = 1024 * lmul // eew
            full = min(65, maximum // 2 if kind == 1 else maximum)
            self.assertGreaterEqual(full, 4)
            edge = min(32 // (eew // 8) + 1, full - 1)
            for reg in (8, 16, 24):
                self.assertEqual(reg % lmul, 0)
                self.assertLessEqual(reg + lmul, 32)
            if kind == 0:
                self.assertLessEqual(2 * lmul, 8)
                self.assertEqual(16 % (2 * lmul), 0)
                self.assertLessEqual(12 + lmul, 16)
                self.assertLessEqual(16 + 2 * lmul, 24)
            if kind == 1:
                self.assertLessEqual(full + edge, maximum)
                self.assertLessEqual(full + edge, 130)
            if kind == 2:
                load_eew = 64 if eew == 8 else 8
                count = (full * eew + load_eew - 1) // load_eew
                self.assertLessEqual(count, 1024 * lmul // load_eew)
                footprint = (2 * (full - 1) + 2) * (eew // 8)
                self.assertLess(footprint, (2 * 65 + 2) * (eew // 8) + 8)

    def test_unsigned_widening_oracle_matches_signed_math(self):
        for eew in (8, 16, 32):
            mask = (1 << eew) - 1
            wide_mask = (1 << (2 * eew)) - 1
            for signed in (False, True):
                for a in (0, 1, mask >> 1, (mask >> 1) + 1, mask):
                    for b in (0, 1, mask >> 1, (mask >> 1) + 1, mask):
                        def extend_bits(x):
                            if signed and x & (1 << (eew - 1)):
                                x |= ((1 << 64) - 1) ^ mask
                            return x
                        def mathematical(x):
                            return x - (1 << eew) if signed and x >> (eew - 1) else x
                        bits = (extend_bits(a) + extend_bits(b)) & wide_mask
                        exact = (mathematical(a) + mathematical(b)) & wide_mask
                        self.assertEqual(bits, exact)
                        self.assertEqual(((bits >> 1) + a) & mask,
                                         ((exact >> 1) + a) % (1 << eew))

    def test_body_uses_scalar_oracle_and_no_segments(self):
        body = (gen.DEST / "vqueue_gap28_body.h").read_text()
        self.assertNotIn("seg", body)
        for insn in ("vslidedown.vx", "vslideup.vx", "vnsrl.wi", "vadd.vv"):
            self.assertIn(insn, body)
        self.assertIn("Q_KIND == 2 && pass == 5", body)
        self.assertIn("sum >> 1", body)
        self.assertIn("wide_output[i], want_wide", body)
        self.assertIn("strided[b], stride_want", body)
        self.assertNotIn("int64_t", body.replace("uint64_t", ""))


if __name__ == "__main__":
    unittest.main()
