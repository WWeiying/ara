import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "memory_gaps", Path(__file__).with_name("generate_rvv_memory_gaps.py"))
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class MemoryGapGeneratorTests(unittest.TestCase):
    def test_selection_and_serial_preflight_order(self):
        selection = json.loads(Path(__file__).with_name(
            "rvv_memory_gap_selection.json").read_text())
        self.assertEqual(selection, {"tests": ["rvv:" + case[0]
                                               for case in GEN.cases()]})
        self.assertEqual(selection["tests"][:2], [
            "rvv:vmemory_gap_nf7_e64_strided", "rvv:vmemory_gap_vloxei64_e8"])

    def test_matrix_and_generated_sources(self):
        cases = list(GEN.cases())
        self.assertEqual(len(cases), 40)
        self.assertEqual(len({case[0] for case in cases}), 40)
        for case in cases:
            self.assertEqual((GEN.DEST / (case[0] + ".c")).read_text(),
                             GEN.render(case))

    def test_complete_segment_instruction_matrix(self):
        forms = set()
        for _, nf, eew, mode, index_eew in GEN.cases():
            forms.update(GEN.instructions(nf, eew, mode, index_eew)[:4])
        for nf in (5, 6, 7):
            for eew in (8, 16, 32, 64):
                for prefix in ("vl", "vs", "vls", "vss"):
                    self.assertIn(f"{prefix}seg{nf}e{eew}.v", forms)
                for prefix in ("vlux", "vlox", "vsux", "vsox"):
                    self.assertIn(f"{prefix}seg{nf}ei{eew}.v", forms)
        self.assertIn("vloxei64.v", forms)

    def test_index_bounds_and_register_legality(self):
        for _, nf, eew, mode, index_eew in GEN.cases():
            self.assertLessEqual(nf, 8)
            self.assertLess(8 + nf - 1, 24)
            emul = index_eew / eew
            self.assertLessEqual(emul, 8)
            self.assertEqual(24 % max(1, emul), 0)
            row = nf if mode == "unit" else nf + 2
            offsets = [((3 * i + 1) % 8) * row * (eew // 8)
                       for i in range(8)]
            self.assertEqual(len(set(offsets)), 8)
            self.assertLess(max(offsets), 1 << index_eew)
            self.assertTrue(all(offset % (eew // 8) == 0 for offset in offsets))


if __name__ == "__main__":
    unittest.main()
