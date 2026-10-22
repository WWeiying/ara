import copy
import unittest
import admit_c910_float_edge_initialized as a


class QualifiedAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=a.life.OUT/'c910-float-edge-initialized-qualified777-parent-20261007-01/qualification.json'
        cls.q=a.life.read_bound(cls.path,'18168c5b7a05081362e4682a7d4fe9ca8bb5662bda4b3a15af2eefc667eef9ae')
        cls.before=a.life.read_bound(a.runner.BASE/'combined-bits.json',
            a.life.read_bound(a.runner.BASE/'admission-manifest.json',a.runner.BASE_SHA)['output_pins'][str(a.runner.BASE/'combined-bits.json')])
        path=cls.path.parent/'single-bits.json'; cls.single=a.life.read_bound(path,cls.q['input_pins'][str(path)])

    def test_actual_147_generic_no_stop_no_skip(self):
        a.native_gate(self.q['native'])

    def test_generic_status_stop_unknown_nonbitexact_rejected(self):
        for key,value in [('status','PREFIX'),('stopped_at_spike_index',36997),('skipped_unknown_bytes',576),
                          ('non_bit_exact_instructions',1),('unobservable_instructions',1),('first_mismatch',{'byte':0})]:
            n=copy.deepcopy(self.q['native']); n['complete_vector_diff'][key]=value
            with self.assertRaises(ValueError,msg=key): a.native_gate(n)

    def test_incomplete_unretired_trap_and_instruction_unknown_rejected(self):
        for key in ('incomplete_requests','unretired_requests','trapped_requests'):
            n=copy.deepcopy(self.q['native']); n['complete_vector_diff'][key]=[0]
            with self.assertRaises(ValueError,msg=key): a.native_gate(n)
        n=copy.deepcopy(self.q['native']); n['complete_vector_diff']['instructions'][0]['unknown_write_bytes']=1
        with self.assertRaises(ValueError): a.native_gate(n)

    def test_initialization_missing_or_unknown_rejected(self):
        for key,value in [('compared_bytes',32),('unknown_bytes',1),('requests',[])]:
            n=copy.deepcopy(self.q['native']); n['primary']['initialization'][key]=value
            with self.assertRaises(ValueError,msg=key): a.native_gate(n)

    def test_actual_full6162_exact777_prefix(self):
        after=a.full_union(self.before,self.single,self.before)
        path=self.path.parent/'proposed-combined-bits.json'
        self.assertEqual(after,a.life.read_bound(path,self.q['input_pins'][str(path)]))
        self.assertEqual(a.bitmap.delta(self.before,after)['metrics'],dict(line=38,cond=119,branch=38,fsm=0))

    def test_duplicate_or_changed_prefix_rejected(self):
        single=dict(self.single,tests=[self.before['tests'][0]])
        with self.assertRaises(ValueError): a.full_union(self.before,single,self.before)
        before=dict(self.before,tests=['foreign',*self.before['tests'][1:]])
        with self.assertRaises(ValueError): a.full_union(before,self.single,self.before)

    def test_missing_extra_or_shape_changed_rejected(self):
        for case in ('missing','extra','shape'):
            single=copy.deepcopy(self.single); rows=single['metrics']['cond']; scope=next(iter(rows))
            if case=='missing': del rows[scope]
            elif case=='extra': rows['foreign']=copy.deepcopy(rows[scope])
            else: rows[scope]['checksum']='foreign'
            with self.assertRaises(ValueError,msg=case): a.full_union(self.before,single,self.before)


if __name__=='__main__': unittest.main()
