from types import SimpleNamespace
import unittest
import queue_mask_tail_vector_oracle as p

class TailOracleTests(unittest.TestCase):
    def state(self,n):
        c=p.case_context(n);pre={8:c['old8']}
        if c['old9'] is not None:pre[9]=c['old9']
        a=(1<<c['vl'])-1
        post=dict(pre);post[8]=(c['old8']&~a)|c['active_gold']
        return c,pre,post
    def test_all_cases_retained_tail(self):
        total=0
        for n in range(8):
            c,pre,post=self.state(n);total+=p.check_case(n,pre,post)['active_bits_strict']
        self.assertEqual(total,720)
    def test_all_ones_tail(self):
        for n in range(8):
            c,pre,post=self.state(n);post[8]|=p.REGISTER_MASK^((1<<c['vl'])-1)
            p.check_case(n,pre,post)
    def test_mixed_tail(self):
        for n in range(8):
            c,pre,post=self.state(n)
            for bit in range(c['vl'],1024,3):post[8]|=1<<bit
            p.check_case(n,pre,post)
    def test_every_active_bit_flip_rejected(self):
        for n in range(8):
            c,pre,post=self.state(n)
            for bit in range(c['vl']):
                bad=dict(post);bad[8]^=1<<bit
                with self.assertRaises(ValueError):p.check_case(n,pre,bad)
    def test_tail_old1_cannot_clear(self):
        c,pre,post=self.state(0)
        bit=next(i for i in range(c['vl'],1024) if c['old8']>>i&1);post[8]&=~(1<<bit)
        with self.assertRaises(ValueError):p.check_case(0,pre,post)
    def test_v9_corruption(self):
        for n in (1,3,5,7):
            c,pre,post=self.state(n);post[9]^=1
            with self.assertRaises(ValueError):p.check_case(n,pre,post)
    def test_unproved_source(self):
        c,pre,post=self.state(0);pre[8]^=1
        with self.assertRaises(ValueError):p.check_case(0,pre,post)
    def test_unknown_final_byte(self):
        with self.assertRaises(ValueError):p.apply_known_architectural_bytes({8:0},{(8,0):(None,None)})
    def test_hidden_earlier_unknown_write(self):
        bad=SimpleNamespace(be=1,known_be=0,lane=0,eew=0)
        good=SimpleNamespace(be=1,known_be=1,lane=0,eew=0)
        with self.assertRaises(ValueError):p.audit_known_writes([bad,good])
    def test_missing_changed_active_write(self):
        c,pre,post=self.state(0);effective=p.apply_known_architectural_bytes(pre,{})
        with self.assertRaises(ValueError):p.check_case(0,pre,effective)
    def test_identity_no_write(self):
        self.assertEqual(p.apply_known_architectural_bytes({8:123},{}),{8:123})
    def test_transport_preserves_actual_tail(self):
        c,pre,post=self.state(0);actual=dict(post);actual[8]|=p.REGISTER_MASK^((1<<c['vl'])-1)
        p.check_identity_transport(actual,dict(actual))
        with self.assertRaises(ValueError):p.check_identity_transport(actual,post)
    def test_unexpected_register(self):
        c,pre,post=self.state(0);post[10]=1
        with self.assertRaises(ValueError):p.check_case(0,pre,post)

if __name__=='__main__':unittest.main()
