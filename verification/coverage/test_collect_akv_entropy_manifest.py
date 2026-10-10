import copy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import collect_akv_entropy_manifest as c


class ManifestTests(unittest.TestCase):
    def qualified_record(self):
        names = ['conversion-command.json','conversion.log','entropy-ranges.vcd','scalar.json','lifecycle.json',
                 'vector.json','ranges.json','perf.json','contract.json','single-inputs.txt','single-bits.json',
                 'combined-bits-diagnostic.json','raw-delta.json','toggle-gain775.json']
        return dict(status='AKV_ENTROPY_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED',baseline_tests=775,
            native_Spike_comparison=False,software_adapter_not_native=True,scalar_model_skips=0,coverage_admitted=False,
            input_pins={str(c.RUN/'manifest.json'):c.ACTUAL_SHA,'/original':'a'*64},
            output_pins={str(c.OUTPUT/name):'b'*64 for name in names})

    def test_order_only(self):
        self.assertTrue(c.semantic_equal({'pins':{'a':'1','b':'2'}},{'pins':{'b':'2','a':'1'}}))

    def test_semantic_change(self):
        for value in ('changed',False,0):
            self.assertFalse(c.semantic_equal({'pin':True},{'pin':value}))
        self.assertFalse(c.semantic_equal({'pins':{'a':'1'}},{'pins':{'a':'2'}}))

    def test_real_manifest_gate(self):
        actual = c.manifest_gate()
        prepared = c.original.life.read_bound(c.RUN.with_name(c.RUN.name+'.prepared.json'),c.PREPARED_SHA)
        self.assertTrue(c.semantic_equal(actual,prepared))
        self.assertEqual(c.private_life().read_bound(c.RUN/'manifest.json',c.PREPARED_SHA),actual)

    def test_foreign_path_not_translated(self):
        foreign = c.RUN/'foreign.json'
        with patch.object(c.original.life,'read_bound',side_effect=ValueError('original seal reject')) as read:
            with self.assertRaises(ValueError): c.private_life().read_bound(foreign,c.PREPARED_SHA)
            read.assert_called_once_with(foreign,c.PREPARED_SHA)

    def test_wrong_seal_not_translated(self):
        with self.assertRaises(ValueError): c.private_life().read_bound(c.RUN/'manifest.json','0'*64)

    def test_alias_not_translated(self):
        alias = Path(str(c.RUN)+'/../'+c.RUN.name+'/manifest.json')
        with patch.object(c.original.life,'read_bound',side_effect=ValueError('original seal reject')) as read:
            with self.assertRaises(ValueError): c.private_life().read_bound(alias,c.PREPARED_SHA)
            read.assert_called_once_with(alias,c.PREPARED_SHA)

    def test_gate_rejects_changed_semantics(self):
        actual = {'pins':{'a':'1'},'timeout_s':600}
        changed = copy.deepcopy(actual); changed['timeout_s']=601
        with patch.object(c.original.life,'read_bound',side_effect=[actual,changed]):
            with self.assertRaises(ValueError): c.manifest_gate()

    def test_qualification_contract_complete(self):
        q = self.qualified_record()
        pins = c.qualification_contract(q,c.OUTPUT,{'pins':{'/original':'a'*64}})
        self.assertEqual(pins[str(c.RUN/'manifest.json')],c.ACTUAL_SHA)

    def test_wrong_qualification_rejected(self):
        for key,value in [('status','FAILED'),('baseline_tests',776),('scalar_model_skips',False),
                          ('scalar_model_skips',1),('native_Spike_comparison',True),('coverage_admitted',True)]:
            q = self.qualified_record(); q[key]=value
            with self.assertRaises(ValueError): c.qualification_contract(q,c.OUTPUT,{'pins':{'/original':'a'*64}})

    def test_wrong_qualification_manifest_or_pin(self):
        for key in (str(c.RUN/'manifest.json'),'/original'):
            q = self.qualified_record(); q['input_pins'][key]='c'*64
            with self.assertRaises(ValueError): c.qualification_contract(q,c.OUTPUT,{'pins':{'/original':'a'*64}})

    def test_missing_or_foreign_output_rejected(self):
        q = self.qualified_record(); q['output_pins'].pop(str(c.OUTPUT/'ranges.json'))
        with self.assertRaises(ValueError): c.qualification_contract(q,c.OUTPUT,{'pins':{'/original':'a'*64}})
        q = self.qualified_record(); q['output_pins']['/foreign/ranges.json']='d'*64
        with self.assertRaises(ValueError): c.qualification_contract(q,c.OUTPUT,{'pins':{'/original':'a'*64}})

    def test_no_receipt_if_original_collect_fails(self):
        with patch.object(c,'manifest_gate'), patch.object(c,'FunctionType',return_value=lambda *a: (_ for _ in ()).throw(ValueError('original failure'))), \
                patch.object(c,'closure_receipt') as receipt:
            with self.assertRaises(ValueError): c.collect()
            receipt.assert_not_called()

    def test_receipt_only_after_original_return(self):
        order=[]
        with patch.object(c,'manifest_gate'), patch.object(c,'FunctionType',return_value=lambda *a: order.append('original PASS')), \
                patch.object(c,'closure_receipt',side_effect=lambda *a: order.append('receipt')):
            c.collect()
        self.assertEqual(order,['original PASS','receipt'])

    def test_only_fixed_wrapper_removed(self):
        own = str(c.WRAPPER)
        pins = {own:c.ADAPTER_PINS[own],'/extra':'a'*64}
        self.assertEqual(c.original_dependencies(pins),{'/extra':'a'*64})
        self.assertIn(own,pins)
        for wrong in ({'/extra':'a'*64},{own:'0'*64}):
            with self.assertRaises(ValueError): c.original_dependencies(wrong)

    def test_original_import_and_modules_unchanged(self):
        import run_akv_entropy as runner
        original_prepare = runner.prepare
        view = c.private_import('run_akv_entropy')
        self.assertIsNot(view.prepare,original_prepare)
        self.assertIs(runner.prepare,original_prepare)
        self.assertIs(c.private_import('json'),__import__('json'))

    def test_real_prepare_in_wrapper_namespace(self):
        code = '''import collect_akv_entropy_manifest as c
import run_akv_entropy as r
expected = c.manifest_gate()
old_prepare, old_dependencies = r.prepare, r.dependency_pins
view = c.private_runner()
actual = view.prepare(c.RUN, existing=True)[1]
assert c.semantic_equal(actual, expected)
assert len(actual['pins']) == 247
assert r.prepare is old_prepare and r.dependency_pins is old_dependencies
print('REAL_WRAPPER_PREPARE_EXACT247_PASS')
'''
        result = subprocess.run([sys.executable,'-B','-c',code],cwd=c.WRAPPER.parent,
                                capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stdout.strip(),'REAL_WRAPPER_PREPARE_EXACT247_PASS')


if __name__ == '__main__': unittest.main()
