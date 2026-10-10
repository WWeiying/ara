import copy
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import prepare_global776_masku1 as p


class Global776Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = p.life.read_bound(p.Q / 'config.json', p.strict.NATIVE_SHA)
        cls.reference = json.loads((p.Q / 'actual-binding.json').read_bytes())
        cls.family = dict(config=str(p.Q / 'config.json'), config_seal=p.strict.NATIVE_SHA,
            qualified=str(p.Q / 'capture-result.json'), qualified_seal=p.QUAL_SHA,
            receipt=str(p.RECEIPT), receipt_seal=p.RECEIPT_SHA, binding=str(p.Q / 'actual-binding.json'),
            first_EL=str(p.Q / 'first.el'), first_EL_sha256=p.NATIVE_EL_SHA)

    def rows(self, index, stage):
        flags = {b['name']: str(int(stage in ('selected', 'reloaded') and b['role'] == 'target'))
                 for b in self.native['instances'][index]['bindings']}
        return [dict(handle=str(k + 1), path=r[1], meta=r[2], name=r[3], type='logic',
                     coverage='0.00%', display='0', excluded=flags[r[0]])
                for k, r in enumerate(self.reference['scopes'][index])]

    def test_actual_local_EL_closed_source(self):
        native, ref = p.masku(dict(masku776=self.family))
        self.assertEqual(native, self.native); self.assertEqual(ref, self.reference)
        self.assertEqual(p.life.digest(p.Q / 'first.el'), p.NATIVE_EL_SHA)
        self.assertEqual(p.life.digest(p.Q / 'second.el'), p.NATIVE_EL_SHA)
        self.assertEqual(len(p.strict.qualification.records((p.Q / 'first.el').read_text(), native)), 1)

    def test_family_substitution_rejected(self):
        for key in ('config', 'config_seal', 'qualified_seal', 'receipt_seal', 'first_EL_sha256'):
            family = dict(self.family); family[key] = 'other'
            with self.assertRaises(ValueError): p.masku(dict(masku776=family))

    def test_other_three_audited_not_expanded(self):
        result = p.unexpanded_objects(self.native)
        self.assertEqual([r['name'] for r in result],
                         ['deshuffled_vl_bit_mask', 'shuffled_vl_bit_mask', 'bit_enable_mask_o'])
        self.assertTrue(all(r['bits'] == 256 and not r['selected_in776_successor'] for r in result))
        self.assertEqual(result[-1]['disposition'], 'OUTPUT_PORT_PROTECTED_NOT_ADDED')
        bad = copy.deepcopy(self.native)
        child = next(i for i in bad['instances'] if i['scope'] == result[0]['scope'])
        next(b for b in child['bindings'] if b['name'] == result[0]['name'])['role'] = 'target'
        with self.assertRaises(ValueError): p.unexpanded_objects(bad)

    def test_actual_local_five_stages_full987_replay(self):
        for stage in p.STAGES:
            for k in range(26): p.strict.qualification.inventory(p.Q, self.native, stage, k)

    def test_global987_model_five_stages(self):
        for k in range(26):
            before = self.rows(k, 'before')
            for stage in p.STAGES:
                p.masku_rows(self.rows(k, stage), self.native, self.reference, k, stage, before)

    def test_protected_port_array_and_missing_rejected(self):
        child = next(k for k, i in enumerate(self.native['instances']) if i['scope'] == p.strict.qualification.source.prior.SCOPE)
        for k in (0, child):
            rows = self.rows(k, 'selected')
            protected = next(r for r in rows if r['excluded'] == '0')
            protected['excluded'] = '1'
            with self.assertRaises(ValueError): p.masku_rows(rows, self.native, self.reference, k, 'selected')
        rows = self.rows(child, 'selected')
        next(r for r in rows if r['name'] == 'bit_enable_mask_o[255:0]')['excluded'] = '1'
        with self.assertRaises(ValueError): p.masku_rows(rows, self.native, self.reference, child, 'selected')
        with self.assertRaises(ValueError): p.masku_rows(self.rows(0, 'before')[:-1], self.native, self.reference, 0, 'before')

    def test_duplicate_partial_type_drift_and_reset_flags(self):
        mutations = [lambda r: r[1].update(handle=r[0]['handle']),
                     lambda r: r[1].update(name=r[0]['name'], path=r[0]['path'], meta=r[0]['meta']),
                     lambda r: r[0].update(name='partial[0]', path='partial[0]', meta='partial[0]')]
        for mutate in mutations:
            rows = self.rows(0, 'before'); mutate(rows)
            with self.assertRaises(ValueError): p.masku_rows(rows, self.native, self.reference, 0, 'before')
        rows = self.rows(0, 'selected'); rows[0]['type'] = 'wire'
        with self.assertRaises(ValueError): p.masku_rows(rows, self.native, self.reference, 0, 'selected', self.rows(0, 'before'))
        rows = self.rows(0, 'reset'); next(r for r in rows if r['name'] == 'bit_enable_mask[255:0]')['excluded'] = '1'
        with self.assertRaises(ValueError): p.masku_rows(rows, self.native, self.reference, 0, 'reset')

    def test_partition_retains_metrics_and_whole_observer(self):
        retained = 'CHECKSUM: "1"\nINSTANCE: observer\nCHECKSUM: "2 3"\nINSTANCE: functional\nBranch branch "branch"\n'
        text = (p.Q / 'first.el').read_text()
        old, added = p.split_masku(retained + text)
        self.assertEqual(old, retained)
        self.assertEqual(p.strict.qualification.records(added, self.native), p.strict.qualification.records(text, self.native))

    def test_new_metrics_foreign_target_and_duplicate_rejected(self):
        text = (p.Q / 'first.el').read_text()
        for bad in [text + text, text.replace('Toggle ', 'Line '), text.replace('[255:0]', '[127:0]'),
                    text.replace('bit_enable_mask', 'bit_enable_mask_o')]:
            _, added = p.split_masku(bad)
            with self.assertRaises(ValueError): p.strict.qualification.records(added, self.native)

    def test_inherited_private_population_anchors_and_no_run(self):
        text = inspect.getsource(p.prior.check)
        self.assertEqual(text.count("c['population']==775"), 1)
        self.assertEqual(text.count("==775,'Actual775 full population'"), 1)
        with patch.object(p.prior, 'namespace', return_value={'verify': lambda out, seal: None, 'run': lambda: None}):
            ns = p.namespace()
        self.assertNotIn('run', ns)
        self.assertIs(ns['audit_observers'], p.observers)

    def test_retained_policy_change_rejected(self):
        old = dict(schema='old', population=775, policy=dict(protected=986), output='old')
        p.retained_equal(dict(old, population=776, output='new'), old)
        with self.assertRaises(ValueError): p.retained_equal(dict(old, policy=dict(protected=985)), old)

    def test_actual_tcl_hook_five_stages_one_database(self):
        with tempfile.TemporaryDirectory(dir=p.life.OUT) as td:
            text = r'''
set ::env(DVE_COVERAGE_OUTPUT) {@OUT@}
rename source real_source
proc source {path} {
 if {[file tail $path] eq "report_native_full773_branch720.tcl"} {
  proc combo_audit {stage mode active} {set ::active $active; lappend ::retained $mode}
  proc p740_root {} {}
  proc p740_select {scope} {return $scope}
  proc dw_select {path meta} {}
 } else {uplevel 1 [list real_source $path]}
}
set ::retained {}
proc imported {} {real_source {@TCL@}}
imported
set ::full775_mfpu_scopes {}
set ::full775_rvh_scopes {}
set ::full776_masku_scopes {}
for {set n 0} {$n<26} {incr n} {lappend ::full776_masku_scopes s$n}
proc gui_open_cov {args} {error "Second database open forbidden"}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_get_property {args} {
 set n [lindex $args end]; if {$n>=4} {error end}
 return [lindex {Variable Type Coverage Display} $n]
}
proc gui_list_get {args} {
 set i [lsearch -exact $args -text]
 if {$i>=0} {return [lindex {x logic 0.00% 0} [lindex $args [expr {$i+1}]]]}
 if {[lsearch -exact $args -firstChild]>=0} {if {[llength $args]==3} {return 1};return 0}
 if {[lsearch -exact $args -nextSibling]>=0} {return 0}
 return x
}
proc gui_exclusion {args} {return 0}
foreach {stage mode active} {initial before 0 applied selected 1 reset reset 0 reloaded reloaded 1 final final 0} {
 combo_audit $stage $mode $active
}
puts [join $::retained ,]
'''.replace('@OUT@', td).replace('@TCL@', str(p.TCL))
            result = subprocess.run(['tclsh'], input=text, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertIn('before,selected,reset,reloaded,final', result.stdout)
            self.assertEqual(len(list(Path(td).glob('masku776_*.tsv'))), 130)


if __name__ == '__main__': unittest.main()
