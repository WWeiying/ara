from copy import deepcopy
import unittest
import prepare_sv39_masked_unit_fault_gain as m


class GainTests(unittest.TestCase):
    def fixture(self):
        scope='ara_tb.dut.i_ara_soc.i_system'
        before=dict(tests=['/old/%d/code.vdb'%i for i in range(735)],design={'design/x':'a'*64},
                    input_hashes={'/old/metric':'a'*64},metrics={k:{scope:dict(width=2,checksum='1',bits='0x0')}
                    for k in m.bitmap.METRICS})
        single=deepcopy(before);single['tests']=[str(m.qualified.v2.RUN/'code.vdb')]
        single['input_hashes']={'/new/metric':'b'*64};single['metrics']['cond'][scope]['bits']='0x1'
        return before,single

    def test_exact_prefix_positive(self):
        before,single=self.fixture();combined,delta=m.population(before,single)
        self.assertEqual(combined['tests'][:-1],before['tests'])
        self.assertEqual(len(combined['tests']),736)
        self.assertEqual(delta['metrics'],dict(line=0,cond=1,branch=0,fsm=0))

    def test_zero_gain(self):
        before,single=self.fixture();single['metrics']=deepcopy(before['metrics'])
        with self.assertRaises(ValueError):m.population(before,single)

    def test_duplicate_case(self):
        before,single=self.fixture();before['tests'][-1]=single['tests'][0]
        with self.assertRaises(ValueError):m.population(before,single)

    def test_wrong_population(self):
        before,single=self.fixture();before['tests'].pop()
        with self.assertRaises(ValueError):m.population(before,single)

    def test_foreign_single(self):
        before,single=self.fixture();single['tests']=['/foreign/code.vdb']
        with self.assertRaises(ValueError):m.population(before,single)

    def test_shape_drift(self):
        before,single=self.fixture();single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system']['checksum']='2'
        with self.assertRaises(ValueError):m.population(before,single)

    def test_foreign_design(self):
        before,single=self.fixture();single['design']={'other':'a'*64}
        with self.assertRaises(ValueError):m.population(before,single)

    def test_conflicting_shared_pin(self):
        before,single=self.fixture();single['input_hashes']={'/old/metric':'b'*64}
        with self.assertRaises(ValueError):m.population(before,single)

    def test_bool_width(self):
        before,single=self.fixture();before['metrics']['line']['ara_tb.dut.i_ara_soc.i_system']['width']=True
        with self.assertRaises(ValueError):m.population(before,single)

    def qualified(self):
        return dict(result=dict(status='SV39_MASKED_UNIT_FAULT_FULL_SCALAR_RVC_NATIVE_GOLD_PASS_NOT_ADMITTED',
            baseline=735,baseline_seal=m.BASE_SEAL,checks=85,whole_scalar_memory_qualified=True,
            full_scalar_differential_qualified=True,native_DUT_vector_qualified=True,
            bitmap_not_collected=True,coverage_admitted=False,rtl_changed=False))

    def test_complete_qualification(self):m.qualification_gate(self.qualified())

    def test_partial_scalar_or_native_rejected(self):
        for field in ('whole_scalar_memory_qualified','full_scalar_differential_qualified','native_DUT_vector_qualified'):
            q=self.qualified();q['result'][field]=False
            with self.subTest(field=field),self.assertRaises(ValueError):m.qualification_gate(q)

    def test_wrong_baseline_or_admitted_rejected(self):
        for field,value in [('baseline',734),('coverage_admitted',True),('checks',84)]:
            q=self.qualified();q['result'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.qualification_gate(q)


if __name__=='__main__':unittest.main()
