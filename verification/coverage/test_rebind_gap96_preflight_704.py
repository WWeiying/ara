import copy
import unittest

import rebind_gap96_preflight_704 as binding


class FakeDefinition:
    def get(self, key):
        return "checksum"


class FakeDesign:
    def definition(self, scope, metric):
        return FakeDefinition()


class RebindTests(unittest.TestCase):
    def setUp(self):
        self.point = dict(raw_index=0, line="178")
        self.original = dict(rows=[dict(scope="scope", checksum="checksum", width=1,
                                        missing_points=[self.point])])
        self.bitmap = dict(metrics=dict(branch=dict(scope=dict(checksum="checksum", width=1, bits="0x0"))))

    def test_preserve_zero_and_remove_new_hit(self):
        from unittest.mock import patch
        with patch.object(binding, "points", return_value=[self.point]):
            rows = binding.rebind_rows(self.original, self.bitmap, FakeDesign())
            self.assertEqual(rows[0]["missing_points"], [self.point])
            self.bitmap["metrics"]["branch"]["scope"]["bits"] = "0x1"
            rows = binding.rebind_rows(self.original, self.bitmap, FakeDesign())
            self.assertEqual(rows[0]["missing_points"], [])
            self.assertEqual(rows[0]["now_hit_since701"], [self.point])

    def test_reject_shape_change(self):
        for field, value in (("width", 2), ("checksum", "other")):
            bitmap = copy.deepcopy(self.bitmap)
            bitmap["metrics"]["branch"]["scope"][field] = value
            with self.assertRaises(ValueError):
                binding.rebind_rows(self.original, bitmap, FakeDesign())

    def test_reject_point_identity_change(self):
        from unittest.mock import patch
        with patch.object(binding, "points", return_value=[dict(self.point, line="other")]):
            with self.assertRaises(ValueError):
                binding.rebind_rows(self.original, self.bitmap, FakeDesign())


if __name__ == "__main__":
    unittest.main()
