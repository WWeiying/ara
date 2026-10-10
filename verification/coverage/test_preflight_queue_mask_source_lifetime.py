import copy
import unittest
import preflight_queue_mask_source_lifetime as p
import test_preflight_queue_vid_source_lifetime as old

class MaskOracleTests(unittest.TestCase):
    def setUp(self):
        fixture=old.OracleTests();fixture.setUp()
        self.commits=fixture.commits;self.symbols=fixture.symbols
        base=self.symbols['qv_vid']
        for c in self.commits:
            for k,(a,v) in enumerate(c.memory_accesses):
                if base<=a<base+8*288:
                    n,off=divmod(a-base,288)
                    c.memory_accesses[k]=(a,int.from_bytes(p.expected(n,'vid')[off:off+8],'little'))
            if c.pc in [self.symbols['qv_pair_'+str(n)]+4 for n in range(8)]:
                c.instruction=(26<<26)|(1<<25)|(24<<20)|(7<<15)|(4<<12)|(8<<7)|0x57
        self.validate=p.namespace()['validate']
    def test_positive(self):
        self.assertEqual(self.validate(self.commits,self.symbols,'')['checks'],6936)
    def test_wrong_guard(self):
        c=copy.deepcopy(self.commits);c[4].memory_accesses[0]=(c[4].memory_accesses[0][0],0)
        with self.assertRaises(ValueError):self.validate(c,self.symbols,'')
    def test_wrong_mask(self):
        c=copy.deepcopy(self.commits);a=self.symbols['qv_vid']+16
        for x in c:
            if x.memory_accesses and x.memory_accesses[0][0]==a:x.memory_accesses[0]=(a,x.memory_accesses[0][1]^1)
        with self.assertRaises(ValueError):self.validate(c,self.symbols,'')
    def test_wrong_csr(self):
        c=copy.deepcopy(self.commits);a=self.symbols['qv_csr']
        for x in c:
            if x.memory_accesses and x.memory_accesses[0][0]==a:x.memory_accesses[0]=(a,0)
        with self.assertRaises(ValueError):self.validate(c,self.symbols,'')
    def test_vid_not_mask(self):
        c=copy.deepcopy(self.commits);c[-1].instruction=(20<<26)|(1<<25)|(17<<15)|(2<<12)|(8<<7)|0x57
        with self.assertRaises(ValueError):self.validate(c,self.symbols,'')
    def test_no_vrf(self):
        c=copy.deepcopy(self.commits)
        for x in c:x.vector_writes={}
        with self.assertRaises(ValueError):self.validate(c,self.symbols,'')
    def test_missing_bytes(self):
        with self.assertRaises(ValueError):self.validate(self.commits[:4]+self.commits[5:],self.symbols,'')
    def test_trap(self):
        with self.assertRaises(ValueError):self.validate(self.commits,self.symbols,'exception trap_illegal_instruction')
    def test_independent_mask_bits(self):
        for n,(sew,lmul) in enumerate(p.prior.CELLS):
            data=p.expected(n,'vid');source=p.expected(n,'source');vl=128*lmul//(sew//8)
            for bit in range(vl):
                self.assertEqual(data[16+bit//8]>>(bit%8)&1,
                    int(int.from_bytes(source[16+bit*(sew//8):16+(bit+1)*(sew//8)],'little')<((1<<sew)-1)//2))
            self.assertEqual(data[16+(vl+7)//8:],source[16+(vl+7)//8:])

if __name__=='__main__':unittest.main()
