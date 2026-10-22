import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import report_native_batch768_v3 as r


class SourceFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items={key:r.source_family(key) for key in sorted(r.FIRST)}
        cls.fixed=r.fixed_family()

    def test_actual_complete_source_before_bound_not_qualified(self):
        expected={'csr1193':2077,'tlb726':None,'accum66':2425}
        for key,item in self.items.items():
            self.assertEqual(item['qualification_origin'],r.ROLE)
            self.assertFalse(item['local_qualified'])
            self.assertIsNone(item['qualification_seal'])
            self.assertTrue(item['reference_pins'])
            if expected[key] is not None:
                self.assertEqual(sum(map(len,item['reference'].values())),expected[key])
            r.origin_gate(key,item)

    def test_premature_local_pass_or_population_application_rejected(self):
        for key,item in self.items.items():
            for field,value in [('local_qualified',True),('qualification_seal','a'*64),
                                ('population_application',True),('reference_pins',{})]:
                bad=copy.deepcopy(item);bad[field]=value
                with self.subTest(key=key,field=field),self.assertRaises(ValueError):
                    r.origin_gate(key,bad)

    def test_reference_drift_rejected(self):
        bad=copy.deepcopy(self.items['accum66'])
        path=next(iter(bad['reference_pins']));bad['reference_pins'][path]='0'*64
        with self.assertRaises(ValueError):r.origin_gate('accum66',bad)

    def test_missing_actual_before_capture_rejected(self):
        with patch.object(r.v2.accum,'inventory',side_effect=ValueError('Missing actual inventory')):
            with self.assertRaises(ValueError):r.source_family('accum66')

    def test_fixed_parent_offline_path_and_exact_partial_bits(self):
        item=self.fixed
        self.assertNotEqual(r.FIXED.parent,r.typed.CAPTURE)
        self.assertEqual(item['output'],str(r.typed.CAPTURE))
        self.assertEqual(item['qualification_seal'],r.FIXED_SHA)
        self.assertEqual(len(item['canonical']),4396)
        self.assertEqual(sum(map(len,item['signals'].values())),120)

    def test_no_authorization_from_source_proof_alone(self):
        for flags in [(False,False),(True,False),(False,True)]:
            with self.assertRaises(ValueError):r.authorize(*flags)
        r.authorize(True,True)

    def test_original_full_verifier_and_exact_scope_selection_retained(self):
        ns=r.namespace()
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertIn('audit_six',ns['verify'].__code__.co_names)
        text=r.TCL.read_text()
        self.assertIn('p740_select [lindex $group 0]',text)
        self.assertNotIn('p740_row',text)

    def test_actual_shared_accumulator_order_diff_is_only_sorting(self):
        c=r.life.read_bound(r.base.BASE/'config.json',r.base.BASE_SHA)
        scope='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_fp_accumulator'
        index=next(n for n,i in enumerate(c['child_config']['instances']) if i['scope']==scope)
        before=c['child_references'][index]
        new=self.items['accum66']['reference'][scope]
        self.assertNotEqual(before,new)
        self.assertEqual(sorted(before),sorted(new))
        self.assertEqual(before[39][0],'gen_schedule_mask[1].eligible')
        self.assertEqual(new[39][0],'gen_schedule_mask[10].eligible')

    def test_actual_generated_all_groups_five_stage_host_flow(self):
        c=r.life.read_bound(r.base.BASE/'config.json',r.base.BASE_SHA)
        read=r.life.OUT/'requester-read108-native767-agent-20261007-01/capture-result.json'
        extra=r.base.additions(False,read,'a31abca542924c82f51f53e4e2c5ed17b22c3476eae035ecdccd5f355dbe749b')
        extra.update(self.items);extra['fixed120']=self.fixed;c['new_families']=extra
        selection=r.life.OUT/'native-batch-full768-v3-prepared-agent-20261007-01/selection.tcl'
        result=r.host_hook(selection,c)
        self.assertEqual(result['stages'],list(r.base.prior.STAGES))
        self.assertFalse(result['EDA_launched'])
        scope=next(iter(self.items['accum66']['reference']))
        c['new_families']['accum66']=copy.deepcopy(self.items['accum66'])
        shared='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_fp_accumulator'
        c['new_families']['accum66']['reference'][shared][0][1]='FOREIGN_META'
        with self.assertRaises(ValueError):r.host_hook(selection,c)


if __name__=='__main__':unittest.main()
