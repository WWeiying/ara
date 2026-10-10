import unittest
import run_gap114_fsm as m


class Oracle(unittest.TestCase):
    def setUp(self):
        self.symbols={'g114_trap_a':1,'g114_trap_b':2,'g114_trap_recovery':3}
        self.values={('g75_result',0):2619,('g75_result',4):0,('num_failed',0):0,('tohost',0):1,('g114_traps',0):8}
        for p in range(4):
            words=[9,1 if p<2 else 2,0,((1<<(24 if p&1 else 12))-1)//3,0x6a39c572e1048dbf]
            recovery=[9,3,0,0,0x13579bdf2468ace0]
            for j,l in enumerate((words,recovery)):
                for i,v in enumerate(l):self.values['g114_ledger',(2*p+j)*40+8*i]=v
            self.values['g114_recovered',8*p]=0x13579bdf2468ace0
            for i in range(512):self.values['g114_guards',p*4096+8*i]=0x13579bdf2468ace0+i
        for i in range(512):self.values['g114_vrf',8*i]=0x0101010101010101*(0x40+i//16)
        for i,v in enumerate((128,0,0,0,0,0)):self.values['g114_csr',8*i]=v
        for i in range(8):self.values['g114_restore',8*i]=0

    def check(self):m.oracle(lambda n,o=0,size=8:self.values.get((n,o)),self.symbols)
    def test_complete_oracle(self):self.check()
    def test_uncommitted_store_rejected(self):
        self.values['g114_guards',2*4096]=1
        with self.assertRaises(ValueError):self.check()
    def test_cancelled_load_register_change_rejected(self):
        self.values['g114_ledger',32]=1
        with self.assertRaises(ValueError):self.check()
    def test_vrf_and_csr_negative(self):
        self.values['g114_vrf',8]=0
        with self.assertRaises(ValueError):self.check()
    def test_csr_negative(self):
        self.values['g114_csr',16]=1
        with self.assertRaises(ValueError):self.check()


if __name__=='__main__':unittest.main()
