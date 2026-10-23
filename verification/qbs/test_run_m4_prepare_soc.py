import unittest

from run_m4_prepare_soc import check_result


class TrialTests(unittest.TestCase):
    valid = ("M4_SOC trial=0 path=generic cycles=100 flags=1 used=0\n"
             "M4_SOC trial=1 path=vector cycles=80 flags=1 used=1\n"
             "M4_SOC trial=2 path=vector cycles=81 flags=1 used=1\n"
             "M4_SOC trial=3 path=generic cycles=101 flags=1 used=0\n"
             "M4_SOC_RESULT errors=0 bytes=3808 inputs=3584 k=896 calls=4 golden=linux_ggml\n")

    def test_complete(self):
        self.assertEqual(len(check_result(self.valid)), 4)

    def test_reject(self):
        for text in ("", self.valid.replace("errors=0", "errors=1"),
                     self.valid.replace("cycles=80", "cycles=0"),
                     self.valid.replace("flags=1 used=1", "flags=0 used=1"),
                     self.valid.replace("trial=3", "trial=2"),
                     self.valid + self.valid, self.valid.replace("golden=linux_ggml", "golden=none")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_result(text)


if __name__ == "__main__":
    unittest.main()
