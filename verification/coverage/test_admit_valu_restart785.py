"""Pure host admission tests; no proposed manifest/admission or EDA."""
import copy
import unittest
import admit_valu_restart785 as s


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.before=dict(design={'shape':'fixed'},tests=['old'+str(i) for i in range(784)],
            input_hashes={'/old':'a'*64},metrics={})
        self.single=dict(design={'shape':'fixed'},tests=[str(s.RUN/'code.vdb')],
            input_hashes={'/new':'b'*64},metrics={})
        for metric,count in s.COUNTS.items():
            self.before['metrics'][metric]={str(i):dict(width=3,checksum='fixed',bits='0x1') for i in range(count)}
            self.single['metrics'][metric]={str(i):dict(width=3,checksum='fixed',bits='0x2') for i in range(count)}

    def test_exact_full_OR(self):
        before=copy.deepcopy(self.before);after=s.full_union(self.before,self.single)
        self.assertEqual(self.before,before);self.assertEqual(after['tests'][:-1],before['tests'])
        self.assertEqual(len(after['tests']),785)
        self.assertTrue(all(r['bits']=='0x3' for rows in after['metrics'].values() for r in rows.values()))

    def test_OR_negatives(self):
        for change in ('old783','duplicate_prefix','duplicate_candidate','design','checksum','width','extra_bit','missing','pin'):
            b,n=copy.deepcopy(self.before),copy.deepcopy(self.single)
            if change=='old783':b['tests'].pop()
            elif change=='duplicate_prefix':b['tests'][0]=b['tests'][1]
            elif change=='duplicate_candidate':b['tests'][0]=n['tests'][0]
            elif change=='design':n['design']['shape']='foreign'
            elif change=='checksum':n['metrics']['fsm']['0']['checksum']='foreign'
            elif change=='width':n['metrics']['fsm']['0']['width']=4
            elif change=='extra_bit':n['metrics']['fsm']['0']['bits']='0x8'
            elif change=='missing':del n['metrics']['fsm']['0']
            else:n['input_hashes']['/old']='c'*64
            with self.subTest(change=change),self.assertRaises(Exception):s.full_union(b,n)

    def test_exact784_prefix(self):
        ledger=[str(s.life.IMAGE)+'.vdb',*self.before['tests']]
        status=dict(aggregate_passed=784,coverage_admitted=True)
        s.ledger_gate(ledger,self.before,status,ledger[:-1])
        wrong=ledger[:-1].copy();wrong[-1]='foreign'
        with self.assertRaises(Exception):s.ledger_gate(ledger,self.before,status,wrong)
        with self.assertRaises(Exception):s.ledger_gate(ledger,self.before,dict(status,aggregate_passed=783),ledger[:-1])

    def test_rebase_never_recounts_prior_hits(self):
        # Serialize near the end of actual-width shape to keep the fixture small.
        row=lambda bits:dict(width=5746,checksum='994898616',bits=hex(bits))
        old={'scope':row(1)};added={'scope':row(2)};single={'scope':row(6)}
        targets=[dict(scope='scope',name='vstart',missing_coordinates=[5744,5743])]
        gain=s.rebased_gain(old,added,single,targets)
        self.assertEqual(gain['actual_new_target_coordinates'],1)
        self.assertEqual(gain['targets'][0]['new_serialized_positions'],[5743])
        no_gain=s.rebased_gain(old,{'scope':row(6)},single,targets)
        self.assertEqual(no_gain['actual_new_target_coordinates'],0)
        self.assertEqual(no_gain['scoped_new_coordinates'],0)

    def test_actual_sealed_architecture(self):
        q=s.life.read_bound(s.QUAL/'qualification.json',s.Q_SHA);s.life.check(q['pins'])
        record=s.case.run.check(s.RUN.with_name(s.RUN.name+'.prepared.json'),s.PREPARED_SHA)
        s.architecture(q,record['preflight'])
        for key,value in [('full_VRF_snapshot_bytes',0),('unknown_defined_bytes_skipped',False),
            ('coverage_admitted',True),('all_scalar_RVC_memory_checked',False)]:
            n=copy.deepcopy(q);n[key]=value
            with self.subTest(key=key),self.assertRaises(Exception):s.architecture(n,record['preflight'])


if __name__=='__main__':unittest.main()
