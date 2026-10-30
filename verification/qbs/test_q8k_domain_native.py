import unittest
from run_q8k_domain_native import check_output


class TestProtocol(unittest.TestCase):
    def test_accept_and_reject(self):
        log="Q8K_DOMAIN_BEGIN vlen=1024\nQ8K_DOMAIN_PASS datasets=134 checks=12060 digest=0123456789abcdef csr=unchanged input=unchanged\nQ8K_DOMAIN_EXIT=0\n"
        self.assertEqual(check_output(log,1024)["checks"],12060)
        for old,new in [("134","133"),("12060","12059"),("EXIT=0","EXIT=1"),("vlen=1024","vlen=128")]:
            with self.subTest(old=old),self.assertRaises(ValueError):check_output(log.replace(old,new),1024)
        with self.assertRaises(ValueError):check_output(log+log,1024)


if __name__=="__main__":unittest.main()
