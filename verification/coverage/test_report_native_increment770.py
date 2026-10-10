import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import report_native_increment770 as r


class ThinAdapterTests(unittest.TestCase):
    def test_missing770_rejects_before_prepare_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'never-created'
            with patch.object(r.frozen,'predecessor_gate',side_effect=AssertionError('Must not reach predecessor')):
                with self.assertRaises(ValueError):r.prepare(output,Path(directory)/'admission-manifest.json','0'*64,'0'*64)
            self.assertFalse(output.exists())

    def test_wrong_baseline_unadmitted_or_wrong_population_rejected(self):
        manifest=r.life.OUT/'synthetic-formal770/admission-manifest.json'
        valid=dict(coverage_admitted=True,baseline=str(r.frozen.FORMAL),baseline_seal=r.frozen.MANIFEST_SHA,
                   input_pins={'/synthetic/input':'a'*64},output_pins={str(manifest.parent/'status.json'):'b'*64})
        status=dict(coverage_admitted=True,aggregate_passed=770)
        for field,value in [('coverage_admitted',False),('baseline','FOREIGN'),('baseline_seal','0'*64)]:
            bad=dict(valid);bad[field]=value
            with patch.object(Path,'is_file',return_value=True),patch.object(r.life,'read_bound',side_effect=[bad,status]):
                with self.assertRaises(ValueError):r.manifest_gate(manifest,'c'*64)
        for value in [769,True,771]:
            bad=dict(status,aggregate_passed=value)
            with patch.object(Path,'is_file',return_value=True),patch.object(r.life,'read_bound',side_effect=[valid,bad]):
                with self.assertRaises(ValueError):r.manifest_gate(manifest,'c'*64)

    def test_pending768_never_creates_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'never-created'
            with patch.object(r,'manifest_gate',return_value=({},{})):
                with self.assertRaises((ValueError,FileNotFoundError)):
                    r.prepare(output,r.life.OUT/'future770/admission-manifest.json','a'*64,'0'*64)
            self.assertFalse(output.exists())

    def test_full6162_shape_or_and_prefix_guards_are_reused(self):
        import inspect
        body=inspect.getsource(r.population)
        self.assertIn('frozen.base.full_or(',body)
        self.assertIn('ledger[:-1]==previous',body)
        self.assertIn('len(selected)==len(set(selected))==770',body)

    def test_actual769_all6162_shape_or_duplicate_negative(self):
        before=json.loads((r.frozen.FORMAL/'combined-bits.json').read_bytes())
        after=copy.deepcopy(before);single=copy.deepcopy(before)
        name='HOST_ONLY_770_NEW_TEST_NOT_ADMISSION'
        after['tests']=before['tests']+[name];single['tests']=[name]
        for rows in single['metrics'].values():
            for row in rows.values():row['bits']='0'
        r.frozen.base.full_or(before,after,single,770)
        self.assertEqual(sum(map(len,before['metrics'].values())),6162)
        bad=copy.deepcopy(after);bad['tests'][-1]=before['tests'][0]
        with self.assertRaises(ValueError):r.frozen.base.full_or(before,bad,single,770)
        metric=next(iter(after['metrics']));scope=next(iter(after['metrics'][metric]))
        for field,value in [('bits',hex(int(after['metrics'][metric][scope]['bits'],16)^1)),('checksum','FOREIGN')]:
            bad=copy.deepcopy(after);bad['metrics'][metric][scope][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):r.frozen.base.full_or(before,bad,single,770)

    def test_substantive_verify_real_terminal_and_source_roles_retained(self):
        ctx=r.context(r.life.OUT/'future770/admission-manifest.json','a'*64)
        ns=ctx['namespace']()
        self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertIs(ctx['predecessor_gate'],r.frozen.predecessor_gate)
        self.assertIs(ctx['real_terminal'],r.frozen.real_terminal)
        self.assertIs(ctx['new_families'],r.frozen.new_families)
        with self.assertRaises(ValueError):r.frozen.inherited.authorize(True,False)

    def test_actual_generated770_entry_five_stage_host(self):
        old=r.frozen; c=old.life.read_bound(old.PREDECESSOR/'config.json',old.PREDECESSOR_SHA)
        c=copy.deepcopy(c);c['new_families'].update(old.new_families())
        ctx=r.context(r.life.OUT/'future770/admission-manifest.json','a'*64)
        private=ctx['private_namespace']()
        text=(old.PREDECESSOR/'selection.tcl').read_text()+old.base.prior.selection_tail(
            dict(c,observer_captures=private['merged_observers'](c)))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'selection.tcl';path.write_text(text)
            result=private['host_hook'](path,c)
        self.assertEqual(result['stages'],list(old.base.prior.STAGES))
        self.assertFalse(result['EDA_launched'])


if __name__=='__main__':unittest.main()
