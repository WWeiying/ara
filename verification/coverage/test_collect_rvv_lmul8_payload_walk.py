import unittest
import collect_rvv_lmul8_payload_walk as p

def row(event,seq=0):
    return dict(event=event,order=str(seq),trans_id='0',insn='0x02000457',trap='0',port='0')

class Gates(unittest.TestCase):
    def test_no_backend_rejected(self):
        with self.assertRaises(ValueError):p.lifecycle([],[])
    def test_missing_response_rejected(self):
        with self.assertRaises(ValueError):p.lifecycle([row('arch_start'),row('cvx_req')],[])
    def test_exception_rejected(self):
        r=row('arch_start');r['trap']='1'
        with self.assertRaises(ValueError):p.lifecycle([r],[])
    def test_complete_conservation(self):
        rows=[row(x) for x in ('arch_start','cvx_req','uop_alloc','uop_done','cvx_resp','retire')]
        vector=[dict(event=x,arch_seq='0',nr_lanes='4',vlen_bits='1024',vid='0',insn='0x02000457')
                for x in ('alloc','write','done')]
        self.assertEqual(p.lifecycle(rows,vector),dict(requests=1,responses=1,exceptions=0,backend=1))
    def test_vector_owner_rejected(self):
        rows=[row(x) for x in ('arch_start','cvx_req','uop_alloc','uop_done','cvx_resp','retire')]
        vector=[dict(event='write',arch_seq='1',nr_lanes='4',vlen_bits='1024',vid='0',insn='0x02000457')]
        with self.assertRaises(ValueError):p.lifecycle(rows,vector)
    def test_initial_config_not_a_product_request(self):
        rows=[row(x) for x in ('arch_start','cvx_req','uop_alloc','uop_done','cvx_resp','retire')]
        config=dict(event='config',cycle='0',arch_seq='0',nr_lanes='4',vlen_bits='1024',
                    insn='00000000',be='00',wdata='0000000000000000')
        vector=[config]+[dict(event=x,arch_seq='0',nr_lanes='4',vlen_bits='1024',vid='0',insn='0x02000457')
                          for x in ('alloc','done')]
        self.assertEqual(p.lifecycle(rows,vector)['backend'],1)
        config['be']='01'
        with self.assertRaises(ValueError):p.lifecycle(rows,vector)

if __name__=='__main__':unittest.main()
