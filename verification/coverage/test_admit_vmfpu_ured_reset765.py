"""Actual sealed reset/764 fixtures; negative admission gates, no simulator or DVE."""
import copy
import json
import unittest
import admit_vmfpu_ured_reset765 as m


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((m.BASE/'combined-bits.json').read_bytes())
        cls.prefix=json.loads((m.post.old.BASE/'combined-bits.json').read_bytes())
        cls.single=json.loads((m.QUAL/'single-bits.json').read_bytes())
        cls.q=m.life.read_bound(m.QUAL/'qualification.json',m.QUAL_SHA)
        cls.scalar=json.loads((m.QUAL/'recovery-scalar.json').read_bytes())
        cls.vector=json.loads((m.QUAL/'recovery-vector.json').read_bytes())
        cls.owners=json.loads((m.QUAL/'cancelled-owner-bindings.json').read_bytes())
        cls.frontend=json.loads((m.QUAL/'frontend-audit.json').read_bytes())

    def check(self,q=None,scalar=None,vector=None,owners=None,frontend=None):
        m.contract(self.q if q is None else q,self.scalar if scalar is None else scalar,
                   self.vector if vector is None else vector,self.owners if owners is None else owners,
                   self.frontend if frontend is None else frontend)

    def test_actual_complete_contract(self):self.check()

    def test_actual764_to765_all_OR(self):
        combined,delta=m.merge(self.before,self.single,self.prefix)
        self.assertEqual(combined['tests'],self.before['tests']+self.single['tests'])
        self.assertEqual(delta['metrics'],dict(line=0,cond=0,branch=0,fsm=4))

    def test_no_duplicate_or_reordered_population(self):
        for action in ('duplicate','reorder'):
            before=copy.deepcopy(self.before)
            if action=='duplicate':before['tests'][-1]=before['tests'][0]
            else:before['tests'][0],before['tests'][1]=before['tests'][1],before['tests'][0]
            with self.subTest(action=action),self.assertRaises(ValueError):m.merge(before,self.single,self.prefix)

    def test_candidate_or_design_drift(self):
        for action in ('candidate','design','shape','missing'):
            single=copy.deepcopy(self.single)
            if action=='candidate':single['tests']=['/wrong/code.vdb']
            elif action=='design':single['design']={}
            elif action=='shape':next(iter(single['metrics']['fsm'].values()))['checksum']='0'
            else:single['metrics']['fsm'].pop(next(iter(single['metrics']['fsm'])))
            with self.subTest(action=action),self.assertRaises(ValueError):m.merge(self.before,single,self.prefix)

    def test_zero_or_already_hit_reset_rejected(self):
        before=copy.deepcopy(self.before)
        for path in m.post.old.states():
            row=before['metrics']['fsm'][path.rsplit('.',1)[0]];row['bits']=hex(int(row['bits'],16)|(1<<17))
        with self.assertRaises(ValueError):m.merge(before,self.single,self.prefix)

    def test_full_checks_or_bool_count(self):
        for key,value in [('checks',True),('epoch0_seed_bytes',4223),('CSR_flags0',False),('coverage_admitted',True)]:
            q=copy.deepcopy(self.q);q[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(q=q)

    def test_cancelled_owner_or_PC_drift(self):
        for key in ('arch_seq','vid','pc','eew','vd','insn'):
            owners=copy.deepcopy(self.owners);owners[0][key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(owners=owners)

    def test_extra_exception_or_cancelled_request(self):
        frontend=copy.deepcopy(self.frontend);frontend[1]['counts']['exceptions']=1
        with self.assertRaises(ValueError):self.check(frontend=frontend)
        q=copy.deepcopy(self.q);q['backend'][1]['aborted']=1
        with self.assertRaises(ValueError):self.check(q=q)

    def test_scalar_or_unknown_vector_drift(self):
        scalar=copy.deepcopy(self.scalar);scalar['matched_instructions']-=1
        with self.assertRaises(ValueError):self.check(scalar=scalar)
        for key in ('skipped_unknown_bytes','unobservable_instructions','non_bit_exact_instructions'):
            vector=copy.deepcopy(self.vector);vector[key]=1
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(vector=vector)


if __name__=='__main__':unittest.main()
