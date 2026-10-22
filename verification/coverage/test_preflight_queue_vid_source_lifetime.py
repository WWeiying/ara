import copy
from types import SimpleNamespace
import unittest
import preflight_queue_vid_source_lifetime as p

class OracleTests(unittest.TestCase):
    def setUp(self):
        names=['tohost','g75_result','num_failed','qv_source','qv_div','qv_vid','qv_csr']
        self.symbols={n:0x80010000+i*0x10000 for i,n in enumerate(names)}
        self.commits=[]
        def store(name,offset,value,width=8):
            self.commits.append(SimpleNamespace(pc=0x80000000,instruction=(0x23 | {1:0,4:2<<12,8:3<<12}[width]),
                memory_accesses=[(self.symbols[name]+offset,value)],vector_writes={}))
        store('tohost',0,1);store('g75_result',0,p.CHECKS,4);store('g75_result',4,0,4);store('num_failed',0,0,4)
        for n,(sew,lmul) in enumerate(p.CELLS):
            for kind in ['source','div','vid']:
                data=p.expected(n,kind)
                for off in range(0,288,8):store('qv_'+kind,n*288+off,int.from_bytes(data[off:off+8],'little'))
            for j,value in enumerate((128*lmul//(sew//8),(sew.bit_length()-4)*8+(lmul==2),0)):
                store('qv_csr',n*24+j*8,value)
            pc=0x80002000+n*8;self.symbols['qv_pair_'+str(n)]=pc
            div=(32<<26)|(1<<25)|(8<<20)|(5<<15)|(6<<12)|(16<<7)|0x57
            vid=(20<<26)|(1<<25)|(17<<15)|(2<<12)|(8<<7)|0x57
            for at,word in [(pc,div),(pc+4,vid)]:
                self.commits.append(SimpleNamespace(pc=at,instruction=word,memory_accesses=[],vector_writes={8:0}))

    def test_full_fixture(self):
        self.assertEqual(p.validate(self.commits,self.symbols,'')['checks'],6936)
    def test_all_eew_lmul_models(self):
        for n,(sew,lmul) in enumerate(p.CELLS):
            size=sew//8;count=128*lmul//size
            div=p.expected(n,'div');vid=p.expected(n,'vid')
            for i in range(count):
                self.assertEqual(int.from_bytes(div[16+i*size:16+(i+1)*size],'little'),(((1<<sew)-1-13*i)%(1<<sew))//3)
                self.assertEqual(int.from_bytes(vid[16+i*size:16+(i+1)*size],'little'),i)
    def test_wrong_buffer(self):
        c=copy.deepcopy(self.commits);c[4].memory_accesses[0]=(c[4].memory_accesses[0][0],0)
        with self.assertRaises(ValueError):p.validate(c,self.symbols,'')
    def test_missing_byte(self):
        with self.assertRaises(ValueError):p.validate(self.commits[:4]+self.commits[5:],self.symbols,'')
    def test_trap(self):
        with self.assertRaises(ValueError):p.validate(self.commits,self.symbols,'exception trap_illegal_instruction')
    def test_no_vrf(self):
        c=copy.deepcopy(self.commits)
        for x in c:x.vector_writes={}
        with self.assertRaises(ValueError):p.validate(c,self.symbols,'')
    def test_wrong_pair_opcode(self):
        c=copy.deepcopy(self.commits);c[-1].instruction^=1<<26
        with self.assertRaises(ValueError):p.validate(c,self.symbols,'')
    def test_missing_pair(self):
        with self.assertRaises(ValueError):p.validate(self.commits[:-1],self.symbols,'')
    def test_unknown_store(self):
        c=copy.deepcopy(self.commits);c[0].instruction=0x13
        with self.assertRaises(ValueError):p.validate(c,self.symbols,'')

if __name__=='__main__':unittest.main()
