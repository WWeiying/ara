import copy
import unittest

from audit_pack_projection import compare


class ComparisonTests(unittest.TestCase):
    def pair(self):
        result = {key: "same" for key in ("checksum", "k", "rows", "inputs", "outputs", "tiles",
                  "operations", "quantizations", "activation_context", "logical_read_bytes", "timing_scope")}
        result.update(quantize_cycles="10", pack_cycles="30", matmul_cycles="60", timed_cycles="100")
        baseline = dict(image_pins_sha256="image", projection=dict(result=result))
        candidate = copy.deepcopy(baseline)
        candidate["projection"]["result"].update(pack_cycles="10", timed_cycles="80")
        return baseline, candidate

    def test_matching(self):
        result = compare(*self.pair())
        self.assertEqual(result["total_speedup"], 1.25)
        self.assertEqual(result["total_cycle_reduction_percent"], 20)

    def test_reject_image_and_work_changes(self):
        for field in ("image", "checksum", "k", "inputs", "timing_scope", "logical_read_bytes"):
            baseline, candidate = self.pair()
            if field == "image":
                candidate["image_pins_sha256"] = "other"
            else:
                candidate["projection"]["result"][field] = "other"
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare(baseline, candidate)


if __name__ == "__main__":
    unittest.main()
