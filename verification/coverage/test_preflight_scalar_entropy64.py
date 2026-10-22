from types import SimpleNamespace
import unittest
import preflight_scalar_entropy64 as p


class Oracle(unittest.TestCase):
    def fixture(self):
        symbols={n:0x80002000+0x1000*i for i,n in enumerate(
            ('entropy_results','entropy_memory','entropy_csrs','g75_result','num_failed','tohost','trap_fail'))}
        writes={}
        for phase in range(3):
            for lane in range(8):
                for op,x in enumerate(p.gold(phase,lane)):
                    writes[symbols['entropy_results']+8*((phase*8+lane)*8+op)]=x
        for lane in range(8):
            for w,x in enumerate(p.words(2,lane)):writes[symbols['entropy_memory']+8*(lane*8+w)]=x
        for i in range(12):writes[symbols['entropy_csrs']+8*i]=i%6
        writes.update({symbols['g75_result']:390,symbols['g75_result']+4:0,
                       symbols['num_failed']:0,symbols['tohost']:1})
        row=SimpleNamespace(pc=0x80000000,vector_writes={},gpr_writes={},memory_accesses=list(writes.items()))
        return row,symbols,writes

    def test_full_matrix(self):
        row,s,_=self.fixture();self.assertEqual(p.validate([row],s)['result_words'],192)

    def test_complement_and_recovery(self):
        for lane in range(8):
            self.assertEqual(p.words(0,lane),p.words(2,lane))
            for x,y in zip(p.words(0,lane)[1:7],p.words(1,lane)[1:7]):self.assertEqual(x^y,p.MASK)

    def test_integer_high_product_and_division(self):
        for phase in range(3):
            for lane in range(8):
                x,y=p.words(phase,lane)[1:3];y|=1;r=p.gold(phase,lane)
                self.assertEqual((r[6]<<64)|r[3],x*y)
                self.assertEqual(r[4]*y+r[5],x)

    def test_changed_result_guard_csr_and_terminal_rejected(self):
        for name,index in [('entropy_results',0),('entropy_memory',0),('entropy_csrs',6),('g75_result',0),('tohost',0)]:
            row,s,w=self.fixture();w[s[name]+8*index]^=1;row.memory_accesses=list(w.items())
            with self.assertRaises(ValueError):p.validate([row],s)

    def test_missing_result_rejected(self):
        row,s,w=self.fixture();del w[s['entropy_results']];row.memory_accesses=list(w.items())
        with self.assertRaises(ValueError):p.validate([row],s)

    def test_trap_or_vector_write_rejected(self):
        row,s,_=self.fixture();row.pc=s['trap_fail']
        with self.assertRaises(ValueError):p.validate([row],s)
        row.pc=0;row.vector_writes={1:2}
        with self.assertRaises(ValueError):p.validate([row],s)


if __name__=='__main__':unittest.main()
