import copy
import csv
from pathlib import Path
import tempfile
import tkinter
import unittest
import half_fma816_native as q


def text(c,prefix=False,split=False):
    rows=[]
    for i in c['instances']:
        rows+=['CHECKSUM: "%s %s"' % (i['design_module_checksum'],i['toggle_checksum']),'INSTANCE: '+i['scope']]
        for t in i['targets']:
            dims=''.join('[%d:%d]' % tuple(d) for d in t['dimensions'])
            decl=dims+t['name'] if prefix else t['name']+dims
            for direction in ('0to1','1to0') if split else ('',):
                rows.append('Toggle '+(direction+' ' if direction else '')+t['name']+' "logic '+decl+'"')
    return '\n'.join(rows)+'\n'


class HalfNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=dict(instances=q.instances(),functional_qualification_seal=q.QUAL_SHA,
                   population_application=False,timeout_seconds=1800)
        cls.text=text(cls.c)

    def test_full_qualified_source_and_capacity(self):
        q.contract(self.c);self.assertEqual(q.evidence()['FMA_observations']['accepted'],224)
        self.assertEqual(sum(len(i['protected']) for i in self.c['instances']),3520)
        self.assertEqual(sum(t['logical_bits'] for i in self.c['instances'] for t in i['targets']),12464)

    def test_typed_whole_and_pair_all816(self):
        records=q.parse_el(self.text,self.c);self.assertEqual(len(records),816)
        self.assertEqual(records,q.parse_el(text(self.c,prefix=True),self.c))
        self.assertEqual(records,q.parse_el(text(self.c,split=True),self.c))

    def test_all_source_target_dimensions_mutated(self):
        for t in self.c['instances'][0]['targets']:
            for index,pair in enumerate(t['dimensions']):
                dims=copy.deepcopy(t['dimensions']);dims[index][0]+=1
                good='"logic '+t['native_name']+'"'
                bad='"logic '+t['name']+''.join('[%d:%d]' % tuple(d) for d in dims)+'"'
                self.assertIn(good,self.text);mutated=self.text.replace(good,bad,1)
                self.assertNotEqual(mutated,self.text)
                with self.assertRaises(ValueError):q.parse_el(mutated,self.c)

    def test_controls_interface_round_flags_otherformat_rejected(self):
        for name in ('rnd_mode_i','out_valid_o','mask_i','status_o','pre_round_mantissa'):
            with self.assertRaises(ValueError):q.parse_el(self.text+'Toggle '+name+' "logic '+name+'"\n',self.c)
        for good,bad in (('2490155775','2490155776'),('2431620414','2431620415'),
                         ('gen_parallel_slices[2]','gen_parallel_slices[0]'),('"logic product','"wire product')):
            mutated=self.text.replace(good,bad,1);self.assertNotEqual(mutated,self.text)
            with self.assertRaises(ValueError):q.parse_el(mutated,self.c)

    def test_missing_duplicate_partial_metric_rejected(self):
        first=next(l for l in self.text.splitlines() if l.startswith('Toggle '))
        for bad in (self.text.replace(first+'\n','',1),self.text+'\n'+first,
                    self.text.replace(first,first.replace('Toggle ','Toggle 0to1 ',1),1),
                    self.text.replace(first,first.replace('Toggle ','Condition ',1),1)):
            with self.assertRaises(ValueError):q.parse_el(bad,self.c)

    def test_config_drift(self):
        c=copy.deepcopy(self.c);c['instances'][0]['targets'][0]['dimensions'][0][1]+=1
        with self.assertRaises(ValueError):q.contract(c)

    def test_relative_review_pins_absolute_complete_conflict_rejected(self):
        review=q.life.read_bound(q.REVIEW,q.REVIEW_SHA)
        pins=q.review_pins(review);self.assertEqual(len(pins),6)
        self.assertTrue(all(Path(p).is_absolute() for p in pins));q.life.check(pins)
        bad=copy.deepcopy(review);name=next(iter(bad['pins']))
        bad['pins'][str((q.life.ROOT/name).resolve())]='0'*64
        with self.assertRaises(ValueError):q.review_pins(bad)
        for name in ('../outside','/tmp/outside'):
            with self.assertRaises(ValueError):q.review_pins(dict(pins={name:'0'*64}))

    def test_full_stage_complement_and_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for stage in q.STAGES:
                (out/q.EL_FILES[stage]).write_text(self.text if stage in ('apply','reload') else '')
                for index,i in enumerate(self.c['instances']):
                    with (out/('native_%s_%d.tsv' % (stage,index))).open('w',newline='') as f:
                        w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(['handle','path','meta','name'])
                        for n,t in enumerate(i['targets']+i['protected']):w.writerow([str(n+1),t['native_name'],t['native_name'],t['native_name']])
                self.assertEqual(q.check_stage(out,stage,self.c)['protected_local_objects'],3520)
            p=out/'native_final_0.tsv';p.write_text(p.read_text().replace('rnd_mode_i[2:0]','BAD_ROUND_MODE'))
            with self.assertRaises(ValueError):q.check_stage(out,'final',self.c)
            (out/'final-empty.el').write_text(self.text)
            with self.assertRaises(ValueError):q.check_stage(out,'final',self.c)

    def test_complete_pinned_Tcl_entry_host_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);t=tkinter.Tcl();t.eval('set ::half816_test_only 1')
            t.eval((q.HERE/'half_fma816_native.tcl').read_text())
            t.setvar('env(DVE_COVERAGE_OUTPUT)',str(out));t.setvar('env(FMA_EXPANDED_CONFIG_SEAL)','host_model_not_actual')
            lines=['set %s {model}\n' % k for k in ('fma_design','fma_vdb','fma_test','fma_python','fma_helper')]
            lines+=['set fma_instances {}\n']
            for index,i in enumerate(self.c['instances']):
                lines.append('lappend fma_instances [list {%s} {%s} %d]\n' %
                             (i['scope'],' '.join(x['native_name'] for x in i['targets']),index))
            (out/'selection.tcl').write_text(''.join(lines))
            t.eval('''
set exclusions 0; set selected {}; set stages {}
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_exclusion {args} {if {[lsearch -exact $args -reset]>=0} {set ::exclusions 0}}
proc gui_process_events {args} {}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclude_items {args} {incr ::exclusions}
proc gui_list_get_selected {args} {
    if {[lsearch -exact $args -count]>=0} {return [llength $::selected]}
    return $::selected
}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc gui_exclusion_file {args} {set ::exclusions 816}
proc fma_bind {stage instance} {
    set rows {}
    foreach name [lindex $instance 1] {lappend rows [list $name $name $name]}
    return $rows
}
proc fma_stage {stage name} {
    lappend ::stages $stage
    if {![info exists ::fma_python] || ![info exists ::fma_helper]} {error "Session globals missing"}
    if {$stage eq "apply" || $stage eq "reload"} {
        if {$::exclusions!=816} {error "Not816 exact selected objects"}
    } elseif {$::exclusions!=0} {error "Not empty reset"}
}
fma_session
''')
            self.assertEqual(t.eval('set stages'),'initial apply reset reload final')
            self.assertEqual(t.eval('set exclusions'),'0')
            self.assertNotIn('FP32/FP64',t.eval('info body fma_session'))


if __name__ == '__main__':unittest.main()
