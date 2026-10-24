"""Host checks of acceptance, not a substitute for the VCS unit."""
import unittest
from run_unit import NEGATIVES, check_log

POSITIVE = ("SHARED_READER_UNIT_PASS cases=10 faults=4 completions=7 bytes=4247 "
            "clears=10 compared_cycles=400\n")


class AcceptanceTests(unittest.TestCase):
    def test_complete_positive(self):
        self.assertEqual(check_log(POSITIVE)["payload_bytes"], 4247)

    def test_incomplete_or_fake_positive(self):
        for text in ("PASS\n", "", POSITIVE * 2, POSITIVE.replace("cases=10", "cases=9"),
                     POSITIVE.replace("cycles=400", "cycles=1"), POSITIVE + "Error: bad\n",
                     POSITIVE + "Fatal: bad\n", POSITIVE.replace("clears=10", "clears=0")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_log(text)

    def test_exact_negative_marker(self):
        for name, marker in NEGATIVES.items():
            self.assertEqual(check_log("Fatal: fixture: " + marker + "\n", name)["rejected"], name)

    def test_wrong_or_multiple_negative(self):
        for name, marker in NEGATIVES.items():
            valid = "Fatal: fixture: " + marker + "\n"
            for text in ("Fatal: unrelated\n", valid * 2, valid + POSITIVE,
                         valid + "Fatal: other\n", valid + "UNIT_TIMEOUT\n",
                         valid + "Error: bad\n", valid + "UNIT_NEGATIVE_NOT_REJECTED\n"):
                with self.subTest(name=name, text=text), self.assertRaises(ValueError):
                    check_log(text, name)


if __name__ == "__main__":
    unittest.main()
