import unittest
from run_shared_mul_llama_soc import parse,EXPECTED


class MicroReportTests(unittest.TestCase):
    def log(self):
        return '\n'.join(f'MICRO {n} PASS cycles=100 actual=0x1 golden=0x1' for n in sorted(EXPECTED))+'\nQ4_K_M micro verification: PASS (0/6 failed)'
    def test_valid(self):self.assertEqual(set(parse(self.log())),EXPECTED)
    def test_missing(self):
        with self.assertRaises(ValueError):parse('MICRO x PASS cycles=100')
    def test_zero(self):
        with self.assertRaises(ValueError):parse(self.log().replace('cycles=100','cycles=0'))
    def test_duplicate(self):
        with self.assertRaises(ValueError):parse(self.log()+'\nMICRO '+sorted(EXPECTED)[0]+' PASS cycles=100')


if __name__=='__main__':unittest.main()
