import runpy
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "coverage"


class ReviewedWaiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        shutil.copyfile(HERE / "prepare_dve_waivers.py", root / "waiver_base.py")
        shutil.copyfile(HERE / "reviewed_20260929/prepare_dve_waivers.py",
                        root / "prepare_dve_waivers.py")
        self.policy = runpy.run_path(str(root / "prepare_dve_waivers.py"))
        self.base = self.policy["base"]

    def test_exact_points(self):
        text = (HERE / "waivers/operand_flush.el").read_text()
        text += "\n" + (HERE / "reviewed_20260929/constant_inputs.el").read_text()
        self.assertEqual(self.base.exclusion_items(text), self.base.approved_points())
        self.assertEqual(len(self.base.approved_points()), 94)

    def test_scope_and_directive_rejection(self):
        for text in ('INSTANCE: other\nToggle ipi_i "net ipi_i"',
                     'INSTANCE: ' + self.policy["ROOT"] + '\nToggle flush_i "net flush_i"',
                     'INSTANCE: other\nCondition 1'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.base.exclusion_items(text)

    def test_missing_point_is_not_approved(self):
        text = (HERE / "waivers/operand_flush.el").read_text()
        self.assertNotEqual(self.base.exclusion_items(text), self.base.approved_points())

    def test_only_current_design_approved(self):
        self.assertEqual(len(self.base.APPROVED), 1)
        self.assertEqual(len(self.base.SHAPES), 1)
        self.assertIn("cva6_rvfi_probes", self.base.MONITORS)


if __name__ == "__main__":
    unittest.main()
