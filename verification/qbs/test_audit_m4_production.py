import importlib.util
from pathlib import Path
import unittest

from audit_m4_production import check_log

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "m4_production_test_fixture", HERE / "ggml_m4_prepare_production/test_check.py")
fixture = importlib.util.module_from_spec(spec)
# The original fixture imports its co-located checker by name.
import sys
sys.path.insert(0, str(HERE / "ggml_m4_prepare_production"))
spec.loader.exec_module(fixture)


class StrictProductionAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = fixture.evidence()
        cls.native = cls.good.split("M4_PRODUCTION_GRAPH_BEGIN", 1)[0] + \
            "M4_PRODUCTION_NATIVE_GUEST_EXIT=0"

    def test_valid_graphs(self):
        self.assertEqual(check_log(self.good, 1024)["graphs"], 384)

    def test_valid_native(self):
        self.assertEqual(check_log(self.native, 128)["checks"], 3420)

    def test_exact_marker_names(self):
        for marker in ("M4_PRODUCTION_BYTES_PASS", "M4_PRODUCTION_NATIVE_BEGIN",
                       "M4_PRODUCTION_NATIVE_END", "M4_PRODUCTION_GRAPH_BEGIN",
                       "M4_PRODUCTION_GRAPH_END", "M4_PRODUCTION_GUEST_EXIT"):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                check_log(self.good.replace(marker, marker + "_BOGUS", 1), 1024)

    def test_embedded_marker(self):
        with self.assertRaises(ValueError):
            check_log(self.good.replace("M4_PRODUCTION_BYTES_PASS", "noise M4_PRODUCTION_BYTES_PASS"), 1024)

    def test_extra_fields(self):
        with self.assertRaises(ValueError):
            check_log(self.good.replace("vcsr=exact", "vcsr=exact unchecked=1", 1), 1024)

    def test_counts_and_path_still_checked(self):
        with self.assertRaises(ValueError):
            check_log(self.good.replace("path=rvv", "path=generic", 1), 1024)

    def test_truncated(self):
        with self.assertRaises(ValueError):
            check_log(self.good.replace("M4_PRODUCTION_GUEST_EXIT=0", ""), 1024)

    def test_configuration(self):
        with self.assertRaises(ValueError):
            check_log(self.good, 256)


if __name__ == "__main__":
    unittest.main()
