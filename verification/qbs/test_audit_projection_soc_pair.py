"""Checks for pairing and honest cycle/traffic accounting."""
import copy
import unittest

from audit_projection_soc_pair import compare


class PairTests(unittest.TestCase):
    def setUp(self):
        self.direct = dict(image_pins_sha256="same", projection=dict(result=dict(
            checksum="0xa6e8082b37dbf573", timed_cycles="256975",
            logical_read_bytes="974400")))
        self.context = copy.deepcopy(self.direct)
        self.context["projection"]["result"].update(
            timed_cycles="257184", logical_read_bytes="871584")

    def test_savings_are_not_mislabeled_speedup(self):
        result = compare(self.direct, self.context)
        self.assertEqual(result["logical_read_bytes_saved"], 102816)
        self.assertAlmostEqual(result["total_cycle_change_percent"],
                               100 * 209 / 256975)

    def test_different_image_rejected(self):
        self.context["image_pins_sha256"] = "another"
        with self.assertRaises(ValueError):
            compare(self.direct, self.context)

    def test_different_output_rejected(self):
        self.context["projection"]["result"]["checksum"] = "wrong"
        with self.assertRaises(ValueError):
            compare(self.direct, self.context)


if __name__ == "__main__":
    unittest.main()
