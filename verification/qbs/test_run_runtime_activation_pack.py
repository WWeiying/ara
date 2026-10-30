import unittest

from run_runtime_activation_pack import check_log


class RuntimePackLogTest(unittest.TestCase):
    good = ("RUNTIME_PACK_PASS cases=10752 invalid=8 bytes=exact guards=exact fcsr_vcsr=exact\n"
            "RUNTIME_PACK_GUEST_EXIT=0\n")

    def test_complete(self):
        self.assertEqual(check_log(self.good), {"cases": 10752, "invalid_cases": 8})

    def test_rejects_partial_duplicate_or_failure(self):
        for text in (self.good.replace("10752", "10751"), self.good + self.good,
                     self.good.replace("invalid=8", "invalid=7"),
                     self.good.replace("RUNTIME_PACK_GUEST_EXIT=0", "RUNTIME_PACK_GUEST_EXIT=1"),
                     self.good + "RUNTIME_PACK_FAIL line=100\n",
                     self.good + "Kernel panic\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_log(text)


if __name__ == "__main__":
    unittest.main()
