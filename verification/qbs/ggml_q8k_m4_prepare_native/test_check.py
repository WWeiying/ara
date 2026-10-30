import unittest
from check import CASES, check_output


def fixture():
    rows = ["Q8K_M4_BEGIN vlen=128 cases=50"]
    for i, (name, k, eligible) in enumerate(CASES):
        vector = 24 if eligible and k else 0
        rows.append(f"Q8K_M4_CASE_PASS id={i} name={name} k={k} eligible={int(eligible)} "
                    f"checks=120 vector={vector} fallback={120-vector} digest={i:016x}")
    rows.extend(["Q8K_M4_PASS cases=50 checks=6000 vector=936 fallback=5064 bytes=exact "
                 "bsums=exact fcsr=exact vcsr=exact guards=exact", "Q8K_M4_GUEST_EXIT=0"])
    return "\n".join(rows)


class Checks(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(len(CASES), 50)
        self.assertEqual(sum(24 for _, k, e in CASES if k and e), 936)
        self.assertEqual(check_output(fixture(), 128)["checks"], 6000)
        self.assertEqual(check_output(fixture().replace("vlen=128", "vlen=1024"), 1024)["real_cases"], 6)

    def test_protocol_mutations(self):
        good = fixture()
        for old, new in [("Q8K_M4_PASS ", "Q8K_M4_PASS_BOGUS "), ("checks=6000", "checks=5999"),
                         ("vector=24", "vector=0"), ("k=8960", "k=1536"),
                         ("fcsr=exact", "fcsr=unchecked"), ("bsums=exact", "bsums=unchecked"),
                         ("GUEST_EXIT=0", "GUEST_EXIT=1"), ("name=fma_rounding", "name=other")]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_output(good.replace(old, new, 1), 128)

    def test_missing_duplicate_and_failure(self):
        good = fixture()
        rows = good.splitlines()
        for bad in ("\n".join(rows[1:]), "\n".join(rows[:2]+rows[3:]), good+"\n"+rows[2],
                    good+"\nQ8K_M4_FAIL reason=injected", good+"\nKernel panic"):
            with self.assertRaises(ValueError): check_output(bad, 128)

    def test_wrong_vlen(self):
        with self.assertRaises(ValueError): check_output(fixture(), 1024)


if __name__ == "__main__":
    unittest.main()
