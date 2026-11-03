import unittest
from collect_shared_mul_soc import app_regions


class ApplicationRegionTests(unittest.TestCase):
    def test_dotp(self):
        log='SUCCESS.\n'+''.join(f'Calulating {s}b dotp with vectors with length = 8\nVector runtime: 41\nScalar runtime: 101\n' for s in (8,16,32,64))
        self.assertEqual(len(app_regions('dotproduct',log)),4)
    def test_dotp_reject_missing_scalar(self):
        with self.assertRaises(ValueError):app_regions('dotproduct','SUCCESS.\nVector runtime: 41')
    def test_matmul(self):
        log='Calculating a (32 x 32) x (32 x 32) matrix multiplication...\nCalculating imatmul...\nThe execution took 1234 cycles.\nVerifying result...\nPassed.'
        self.assertEqual(app_regions('imatmul',log),{'n32':1234})
    def test_matmul_reject_unchecked(self):
        with self.assertRaises(ValueError):app_regions('imatmul','The execution took 0 cycles.')


if __name__=='__main__':unittest.main()
