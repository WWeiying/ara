import copy
import unittest
import preflight_queue_mask_source_lifetime_tail as p
import test_preflight_queue_mask_source_lifetime as old

class TailTests(unittest.TestCase):
    def setUp(self):
        f=old.MaskOracleTests();f.setUp()
        self.c=f.commits;self.symbols=f.symbols;self.validate=p.namespace()['validate']
        base=self.symbols['qv_vid']
        for c in self.c:
            if not c.memory_accesses:continue
            a,v=c.memory_accesses[0]
            if base<=a<base+8*288:
                n,off=divmod(a-base,288)
                c.memory_accesses[0]=(a,int.from_bytes(p.expected(n,'vid')[off:off+8],'little'))
    def test_complete_fixture(self):
        result=self.validate(self.c,self.symbols,'')
        self.assertEqual(result['strictly_defined_snapshot_bytes'],6912)
        self.assertEqual(result['unobserved_agnostic_VRF_tail_bits'],7472)
    def test_all_active_bits_strict(self):
        for n,(sew,lmul) in enumerate(p.prior.CELLS):
            gold=p.expected(n,'vid')
            for bit in range(128*lmul//(sew//8)):
                bad=bytearray(gold);bad[16+bit//8]^=1<<(bit%8)
                with self.assertRaises(ValueError):p.compare_buffer(n,'vid',bad)
    def test_non_destination_v9_exact(self):
        for n in (1,3,5,7):
            actual=bytearray(p.expected(n,'vid'));actual[144]^=1
            with self.assertRaises(ValueError):p.compare_buffer(n,'vid',actual)
    def test_unwritten_mask_buffer_guard_exact(self):
        actual=bytearray(p.expected(0,'vid'));actual[32]^=1
        with self.assertRaises(ValueError):p.compare_buffer(0,'vid',actual)
    def test_outer_guards_exact(self):
        for offset in (0,15,287):
            actual=bytearray(p.expected(1,'vid'));actual[offset]^=1
            with self.assertRaises(ValueError):p.compare_buffer(1,'vid',actual)
    def test_source_div_exact(self):
        for kind in ('source','div'):
            actual=bytearray(p.expected(0,kind));actual[16]^=1
            with self.assertRaises(ValueError):p.compare_buffer(0,kind,actual)
    def test_tail_policy_old_or_one_only(self):
        self.assertTrue(p.tail_bit_allowed(0,0));self.assertTrue(p.tail_bit_allowed(0,1))
        self.assertTrue(p.tail_bit_allowed(1,1));self.assertFalse(p.tail_bit_allowed(1,0))
    def test_unknown_tail_not_accepted(self):
        with self.assertRaises(ValueError):p.tail_bit_allowed(1,'X')
    def test_no_vrf_rejected(self):
        c=copy.deepcopy(self.c)
        for x in c:x.vector_writes={}
        with self.assertRaises(ValueError):self.validate(c,self.symbols,'')
    def test_trap_rejected(self):
        with self.assertRaises(ValueError):self.validate(self.c,self.symbols,'exception trap_illegal_instruction')
    def test_mask_store_count(self):
        self.assertEqual(sum(128*l//(e//8)//8 for e,l in p.prior.CELLS),90)
        self.assertEqual(p.tail_policy()['non_destination_v9_bytes'],512)
    def test_never_snapshots_agnostic_v8_tail(self):
        for n,(sew,lmul) in enumerate(p.prior.CELLS):
            start=16+128*lmul//(sew//8)//8
            self.assertEqual(p.expected(n,'vid')[start:144],bytes([0xa5])*(144-start))

if __name__=='__main__':unittest.main()
