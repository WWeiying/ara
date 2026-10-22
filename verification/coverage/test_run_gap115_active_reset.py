import unittest
import run_gap115_active_reset as m


class Oracle(unittest.TestCase):
    def setUp(self):
        self.values={('g75_result',0):679,('g75_result',4):0,('num_failed',0):0,('tohost',0):1}
        for i in range(512):self.values['g115_vrf',8*i]=m.expected_word(i)
        for i,v in enumerate((128,27,0,0,0)):self.values['g115_csr',8*i]=v
    def check(self):m.oracle(lambda n,o=0,size=8:self.values.get((n,o)))
    def test_complete(self):self.check()
    def test_wrong_quotient(self):
        self.values['g115_vrf',128*8]=0
        with self.assertRaises(ValueError):self.check()
    def test_wrong_non_destination(self):
        self.values['g115_vrf',24*128]=0
        with self.assertRaises(ValueError):self.check()
    def test_csr(self):
        self.values['g115_csr',16]=1
        with self.assertRaises(ValueError):self.check()
    def test_fixed_no_force_trigger(self):
        self.assertIn('+ARA_UVM_RESET_READ_INDEX=1',m.ARGS)
        source=m.APP.read_text();self.assertIn('.rept 32',source)
        self.assertNotIn('force ',source)


if __name__=='__main__':unittest.main()
