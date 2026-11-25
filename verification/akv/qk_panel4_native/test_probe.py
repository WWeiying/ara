import unittest

from run_probe import classify


class ProbeCheckerTest(unittest.TestCase):
    text = ("AKV_PROBE_BEGIN\nAKV_PROBE_TRAP cause=0000000000000002 "
            "pc=0000000080000400 value=000000000005455b\n")

    def test_exact_blocker(self):
        result = classify(self.text, 2, 0x80000400)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(result["native_panel4_proven"])
        self.assertEqual(result["numerical_cases_executed"], 0)

    def test_rejects_false_evidence(self):
        for text, rc, pc in (
            ("PASS\n", 0, 0x80000400),
            (self.text + "PASS\n", 2, 0x80000400),
            (self.text * 2, 2, 0x80000400),
            (self.text, 0, 0x80000400),
            (self.text, 2, 0x80000404),
            (self.text.replace("5455b", "5785b"), 2, 0x80000400),
            (self.text.replace("cause=0000000000000002", "cause=0000000000000005"), 2, 0x80000400),
            ("", 2, 0x80000400),
        ):
            with self.subTest(text=text, rc=rc, pc=pc):
                with self.assertRaises(RuntimeError):
                    classify(text, rc, pc)


if __name__ == "__main__":
    unittest.main()
