import unittest
from export_q8k_prepare_oracle import check_output


def log():
    lines = ["Q8K_ORACLE_BEGIN m=4 k=1536 bytes=7008", "Q8K_ORACLE_CSR fcsr=1 vcsr=5"]
    for offset in range(0, 7008, 64):
        lines.append(f"Q8K_ORACLE_HEX offset={offset} data=" + "12" * min(64, 7008-offset))
    return "\n".join(lines + ["Q8K_ORACLE_END bytes=7008", "Q8K_ORACLE_EXIT=0"])


class TestOracle(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(check_output(log()), (bytes([18])*7008, 1))

    def test_reject_mutations(self):
        for old, new in [("offset=64", "offset=65"), ("vcsr=5", "vcsr=0"),
                         ("fcsr=1", "fcsr=33"), ("EXIT=0", "EXIT=1"),
                         ("bytes=7008", "bytes=7007"), ("data=12", "data=ff12")]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_output(log().replace(old, new, 1))

    def test_missing_and_duplicate(self):
        with self.assertRaises(ValueError):
            check_output(log().replace("Q8K_ORACLE_EXIT=0", ""))
        with self.assertRaises(ValueError):
            check_output(log() + "\nQ8K_ORACLE_EXIT=0")


if __name__ == "__main__":
    unittest.main()
