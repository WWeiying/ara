import copy
import unittest
import collect_scalar_c910_pattern795_v3 as a
import test_run_collect_scalar_c910_pattern795 as inherited


class FlushOrdering(inherited.Native):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.implementation=staticmethod(a.owner_implementation())

    def flush_output_fixture(self):
        expected,normal=self.fixture()
        flush=copy.deepcopy(normal[2]);flush[1][a.c.SCOPE+'.flush_i']='1'
        flush[1][a.c.ISSUE+'.fpu_valid_n']='0'
        flush[2]={p:'0'*v['width'] for p,v in self.decl.items()}
        reissue=copy.deepcopy(normal[1]);reissue[0]=2.1
        for path in (a.c.SCOPE+'.fpu_valid_i',a.c.SCOPE+'.fpu_gen.fpu_in_valid'):
            reissue[1][path]='0'
        request=copy.deepcopy(normal[2]);request[0]=2.2
        request[1][a.c.SCOPE+'.fpu_valid_o']='0'
        return expected,normal[:2]+[flush,reissue,request]+normal[3:]

    def test_output_then_scheduled_cancel_and_required_reissue(self):
        e,edges=self.flush_output_fixture();r=self.audit(e,edges)
        self.assertEqual(len(r['completed']),4)
        self.assertEqual(r['completed'][0]['flush_edge'],True)
        self.assertEqual(len(r['scheduled_cancellations']),1)
        with self.assertRaises(ValueError):self.audit(e,edges[:3])

    def test_flush_output_wrong_TID_result_flags_rejected(self):
        for name in ('fpu_trans_id_o','result_o','fpu_exception_o'):
            e,edges=self.flush_output_fixture();path=a.c.SCOPE+'.'+name
            value=0 if name!='fpu_exception_o' else 1<<139
            edges[2][1][path]=format(value,'0%db'%self.decl[path]['width'])
            with self.subTest(name=name),self.assertRaises(ValueError):self.audit(e,edges)

    def test_no_output_with_live_owner_rejected(self):
        e,edges=self.flush_output_fixture();edges[2][1][a.c.SCOPE+'.fpu_valid_o']='0'
        with self.assertRaises(ValueError):self.audit(e,edges)

    def test_unknown_active_output_fields_rejected(self):
        for name in ('fpu_valid_o','fpu_trans_id_o','result_o'):
            e,edges=self.flush_output_fixture();path=a.c.SCOPE+'.'+name
            edges[2][1][path]='x'*self.decl[path]['width']
            with self.subTest(name=name),self.assertRaises(ValueError):self.audit(e,edges)
        for field in ('cause','valid','tval'):
            e,edges=self.flush_output_fixture();path=a.c.SCOPE+'.fpu_exception_o'
            left,right=self.proof['exception_layout']['fields'][field]
            bits=list(edges[2][1][path]);width=self.decl[path]['width']
            bits[width-left-1:width-right]='x'*(left-right+1)
            edges[2][1][path]=''.join(bits)
            with self.subTest(field=field),self.assertRaises(ValueError):self.audit(e,edges)

    def test_other_accepted_owner_not_canceled(self):
        e,edges=self.fixture()
        # Keep both accepted FMV owners until flush, completing only the first.
        edges[2][1][a.c.SCOPE+'.fpu_valid_o']='0'
        edges[2][1][a.c.ISSUE+'.fpu_valid_n']='0'
        flush=edges[3][1]
        flush[a.c.SCOPE+'.flush_i']='1';flush[a.c.SCOPE+'.fpu_valid_i']='0'
        flush[a.c.SCOPE+'.fpu_gen.fpu_in_valid']='0'
        flush[a.c.SCOPE+'.fpu_trans_id_o']='001'
        flush[a.c.SCOPE+'.result_o']=format(e[0]['result'],'064b')
        with self.assertRaisesRegex(ValueError,'Flush cannot lose'):self.audit(e,edges)

    def test_held_owner_or_hold_controls_rejected(self):
        for name in ('state_q','fpu_gen.hold_inputs','fpu_gen.use_hold'):
            e,edges=self.flush_output_fixture();edges[2][1][a.c.SCOPE+'.'+name]='1'
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'held owner'):self.audit(e,edges)
        e,edges=self.held(False);edges[4][1][a.c.SCOPE+'.flush_i']='1'
        edges[4][1][a.c.SCOPE+'.fpu_valid_o']='1'
        edges[4][1][a.c.SCOPE+'.fpu_trans_id_o']='011'
        with self.assertRaises(ValueError):self.audit(e,edges)

    def test_actual_first_diagnostic_and_source_identity(self):
        proof=a.source_proof();diag=a.life.read_bound(a.DIAG,a.DIAG_SHA)['evidence']
        self.assertEqual(diag['time'],51095000)
        self.assertEqual(diag['issued'],2);self.assertEqual(len(diag['completed']),1)
        self.assertIsNone(diag['pending']);self.assertIsNone(diag['scheduled'])
        self.assertTrue(diag['live']['0']['accepted'])
        self.assertEqual(diag['before'][a.c.SCOPE+'.fpu_valid_o'],1)
        self.assertEqual(diag['before'][a.c.SCOPE+'.result_o'],diag['live']['0']['result'])
        a.life.check(proof['pins'])


if __name__=='__main__':unittest.main()
