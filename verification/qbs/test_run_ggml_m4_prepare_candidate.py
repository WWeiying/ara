import unittest

from run_ggml_m4_prepare_candidate import check_log


class LogTests(unittest.TestCase):
    valid = ("M4_PREPARE_PASS checks=3375 vector=585 fallback=2790 bytes=exact fcsr=exact\n"
             "M4_CAPTURE_PASS elements=3584 checks=45 vector=9 fallback=36\n"
             "M4_PREPARE_GUEST_EXIT=0\n")

    def test_complete(self):
        self.assertEqual(check_log(self.valid)["checks"], 3375)

    def test_reject_incomplete_and_corrupt(self):
        for text in ("", self.valid.replace("GUEST_EXIT=0", "GUEST_EXIT=1"),
                     self.valid.replace("3375", "3374"),
                     self.valid.replace("vector=585", "vector=0"),
                     self.valid.replace("elements=3584", "elements=0"),
                     self.valid + self.valid,
                     self.valid + "M4_PREPARE_FAIL bad_case\n",
                     self.valid + "Kernel panic - not syncing\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_log(text)


if __name__ == "__main__":
    unittest.main()
