import unittest
from build_q8k_prepare_soc import extract
from run_q8k_prepare_soc import check_result


def log():
    rows = [f"Q8K_SOC trial={i} path={'vector' if i in (1,2) else 'generic'} cycles=100 flags=1 used={int(i in (1,2))}" for i in range(4)]
    return "\n".join(rows+["Q8K_SOC_RESULT errors=0 bytes=7008 inputs=6144 k=1536 calls=4 golden=linux_ggml"])


class TestSoc(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(len(check_result(log())),4)

    def test_errors(self):
        for old,new in [("errors=0","errors=1"),("trial=2","trial=1"),("flags=1","flags=2"),
                        ("cycles=100","cycles=0"),("used=1","used=0"),("bytes=7008","bytes=7007")]:
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_result(log().replace(old,new,1))
        with self.assertRaises(ValueError): check_result(log()+"\n"+log())

    def test_extract(self):
        self.assertEqual(extract("start {}\nend", "start", "end"),"start {}\n")
        for value in ("start { end", "start {} start {} end", "end"):
            with self.assertRaises(ValueError): extract(value,"start","end")


if __name__ == "__main__": unittest.main()
