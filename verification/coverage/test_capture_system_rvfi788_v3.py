import copy
import json
from pathlib import Path
import subprocess
from types import FunctionType, SimpleNamespace
import tempfile
import unittest

import capture_system_rvfi788_v3 as m
from test_capture_system_rvfi788_v2 import StandaloneEntry


class Exact03Entry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        StandaloneEntry.setUpClass();cls.c=copy.deepcopy(StandaloneEntry.c)
        cls.b=m.life.read_bound(m.BINDING,m.BINDING_SHA)
        cls.c.update(binding_sha256=m.BINDING_SHA,native_bindings=cls.b['bindings'],origin_metadata=cls.b['native_identity_rows'],source_review_sha256=cls.b['source_review_sha256'])

    def execute(self,tmp,mutation='',native_mutation=''):
        def run(args,**kwargs):
            out=Path(tmp);c=json.loads((out/'config.json').read_bytes())
            c.update(binding_sha256=m.BINDING_SHA,native_bindings=self.b['bindings'],origin_metadata=self.b['native_identity_rows'],source_review_sha256=self.b['source_review_sha256'])
            (out/'config.json').write_text(json.dumps(c))
            labels=[p['observed_label'] for p in self.b['bindings'] if p['role']=='target']
            labels += [p['observed_label'] for p in self.b['bindings'] if p['role']=='protected']
            selection='set rvfi03_targets [list '+' '.join('{'+label+'}' for label in labels[:788])+']\n'
            (out/'native-binding-selection.tcl').write_text(selection)
            override='set mock_labels [list '+' '.join('{'+label+'}' for label in labels)+']\n'+native_mutation+'\n'
            override += r'''
rename gui_list_get mock_old_list_get
proc gui_list_get {args} {
    if {[lindex $args 1] ne "CoverageTable.1" && [lsearch $args -path]>=0} {
        return [lindex $::mock_labels [expr {[lindex $args end]-1}]]
    }
    return [eval mock_old_list_get $args]
}
rename mock_label mock_old_label
proc mock_label {} {
    set label [lindex $::mock_selection 0]
    if {[lsearch -exact $::mock_labels $label]<0} {error "Foreign singleton label"}
    return $label
}
'''
            require_count=kwargs['input'].count('proc boot {}')
            if require_count!=1:raise AssertionError('Actual standalone entry fixture boundary changed')
            kwargs['input']=kwargs['input'].replace('proc boot {}',override+'proc boot {}')
            return subprocess.run(args,**kwargs)
        facade=SimpleNamespace(HOOK=m.HOOK,__file__=m.__file__,life=m.life,original=m.core)
        worker=FunctionType(StandaloneEntry.execute.__code__,dict(StandaloneEntry.execute.__globals__,
            successor=facade,subprocess=SimpleNamespace(run=run)))
        return worker(self,tmp,mutation)

    def test_actual_sealed_before_inventory(self):
        self.assertEqual(len(m.inventory(m.mapping.ORIGIN,self.c,'before')),1206)

    def test_standalone_full_pipeline_real_aliases_csv_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,out=self.execute(tmp)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)
            self.assertNotIn('SYSTEM_RVFI788_FAILED',p.stdout)
            for stage in ('before','selected','reset','reloaded','final'):
                self.assertEqual(len(m.inventory(out,self.c,stage)),1206)
            self.assertEqual(m.records((out/'first.el').read_text(),self.c),m.records((out/'second.el').read_text(),self.c))
            for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
                self.assertEqual((out/name).read_bytes(),b'')
            import csv
            with (out/'csv-probe.csv').open() as f:self.assertEqual(next(csv.reader(f)),['a,b','x"y','plain'])

    def test_full_protected_metadata_failure_precedes_any_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,out=self.execute(tmp,native_mutation='lset mock_labels end foreign_protected')
            self.assertIn('Missing/foreign full compiled complement',p.stdout)
            self.assertNotIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)
            self.assertFalse((out/'first.el').exists())
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_standalone_bad_reload_does_not_qualify(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,out=self.execute(tmp,'set mock_bad_reload 1')
            self.assertNotIn('SYSTEM_RVFI788_NATIVE_DONE',p.stdout)
            self.assertIn('Target/protected exclusion differs',p.stdout)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_standalone_missing_namespace_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            mutation='rename gui_open_cov mock_open_cov\nproc gui_open_cov {args} {unset ::rvfi_scope;eval mock_open_cov $args}'
            p,out=self.execute(tmp,mutation)
            self.assertIn('SYSTEM_RVFI788_FAILED',p.stdout)
            self.assertFalse((out/'first.el').exists())

    def test_binding_mutation_rejected(self):
        c=copy.deepcopy(self.c);c['native_bindings'][0]['observed_label']='foreign'
        with self.assertRaises(ValueError):m.contract(c)

    def text(self,bare):
        s='CHECKSUM: "'+self.c['module_checksum']+' 3385959260"\nINSTANCE: '+m.core.review.SCOPE+'\nANNOTATION: "'+m.core.ANNOTATION+'"\n'
        for p in self.c['targets']:
            label=p['signal'] if bare and p['signal'] in m.mapping.TARGET_SCALARS else p['native_name']
            s+='Toggle '+p['signal']+' "net '+label+'"\n'
        return s

    def test_exact11_sole_bit_serialization_alias(self):
        self.assertEqual(m.records(self.text(True),self.c),m.records(self.text(False),self.c))

    def test_non_alias_partial_bounds_type_control_rejected(self):
        text=self.text(True)
        for changed in (text.replace('tval[63:0]','tval',1),text.replace('"net ','"reg ',1),
                        text+'Toggle clk_i "net clk_i"\n',text.replace('valid"','valid[1:1]"',1)):
            with self.assertRaises(ValueError):m.records(changed,self.c)


if __name__=='__main__':unittest.main()
