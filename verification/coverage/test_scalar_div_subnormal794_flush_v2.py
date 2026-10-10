import unittest
from pathlib import Path
import scalar_div_subnormal794_flush_v2 as v
from test_scalar_div_subnormal794 import Native


class Cancellation(unittest.TestCase):
    def setUp(self):
        Native.setUpClass();self.fixture=Native();self.decl=Native.decl;self.proof=Native.proof

    def canceled(self):
        expected,normal=self.fixture.fixture()
        issue=[-2,dict(normal[0][1]),dict(normal[0][2])]
        cancel=[-1,dict(normal[1][1]),self.fixture.state()]
        for name in ('fpu_valid_o',):cancel[1][v.old.SCOPE+'.'+name]='0'
        cancel[1][v.old.ISSUE+'.fpu_valid_n']='0';cancel[1][v.old.SCOPE+'.flush_i']='1'
        return expected,[issue,cancel]+normal

    def test_exact_cancel_requires_reissue_and_all_outputs(self):
        e,edges=self.canceled();r=v.audit_edges(self.decl,edges,e,self.proof)
        self.assertEqual(r['issued'],4);self.assertEqual(len(r['completed']),4)
        self.assertEqual(len(r['scheduled_cancellations']),1)

    def test_cancel_bad_used_fields_or_valid_not_cleared_rejected(self):
        for part,path,bits in ((1,v.old.SCOPE+'.fu_data_i','0'*207),
                (2,v.old.SCOPE+'.fpu_valid_i','1'),(1,v.old.SCOPE+'.fpu_valid_o','1'),
                (1,v.old.SCOPE+'.state_q','1')):
            e,edges=self.canceled();edges[1][part][path]=bits
            with self.assertRaises(ValueError):v.audit_edges(self.decl,edges,e,self.proof)

    def test_missing_reissue_rejected(self):
        e,edges=self.canceled()
        with self.assertRaises(ValueError):v.audit_edges(self.decl,edges[:2],e,self.proof)

    def test_live_owner_flush_rejected(self):
        e,edges=self.fixture.fixture();edges[2][1][v.old.SCOPE+'.flush_i']='1'
        with self.assertRaises(ValueError):v.audit_edges(self.decl,edges,e,self.proof)

    def test_held_owner_flush_rejected(self):
        e,edges=self.fixture.held_fixture();edges[4][1][v.old.SCOPE+'.flush_i']='1'
        with self.assertRaises(ValueError):v.audit_edges(self.decl,edges,e,self.proof)

    def test_actual_existing_wave_regression(self):
        pre=v.old.life.read_bound(v.old.runner.PRE/'preflight.json',v.old.runner.PRE_SHA)
        r=v.wave_audit(v.WAVE,v.old.runner.source_contract(),pre)
        self.assertEqual(r['issued'],576);self.assertEqual(len(r['completed']),576)
        self.assertEqual(len(r['table_observations']),144)
        self.assertEqual(r['scheduled_cancellations'][0]['time'],35825000)


if __name__=='__main__':unittest.main()
