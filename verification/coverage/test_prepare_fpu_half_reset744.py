import unittest
from pathlib import Path
import prepare_fpu_half_reset744 as m


class Oracle(unittest.TestCase):
    def setUp(self):
        self.v = {('g75_result', 0): 679, ('g75_result', 4): 0, ('num_failed', 0): 0, ('tohost', 0): 1}
        for i in range(512): self.v['fpar_vrf', 8*i] = m.expected_word(i)
        for i, x in enumerate((512, 11, 0, 0, 33)): self.v['fpar_csr', 8*i] = x

    def check(self): m.oracle(lambda n, o=0, size=8: self.v.get((n, o)))
    def test_complete(self): self.check()
    def test_bad_div(self):
        self.v['fpar_vrf', 384*8] ^= 1
        with self.assertRaises(ValueError): self.check()
    def test_bad_mul(self):
        self.v['fpar_vrf', 128*8] ^= 1
        with self.assertRaises(ValueError): self.check()
    def test_missing_vrf(self):
        del self.v['fpar_vrf', 511*8]
        with self.assertRaises(ValueError): self.check()
    def test_wrong_round_or_flags(self):
        self.v['fpar_csr', 32] = 32
        with self.assertRaises(ValueError): self.check()
    def test_bad_terminal(self):
        self.v['tohost', 0] = 3
        with self.assertRaises(ValueError): self.check()
    def test_no_run_entry(self):
        text = m.APP.read_text()
        self.assertIn('vfdiv.vv v24,v8,v16', text)
        self.assertIn('vle16.v v0', text)
        self.assertIn('.rept 32', text)
        self.assertEqual(text.count('vle'), 1)
        self.assertNotIn('life.run(', Path(m.__file__).read_text())


if __name__ == '__main__': unittest.main()
