"""Exact compiled fixture, corruptions and full Tcl8.4-compatible host lifecycle."""
import copy
import csv
from pathlib import Path
import tempfile
import tkinter
import unittest
import qualify_requester_read108_native as m


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instances=m.instances();cls.c=dict(instances=cls.instances,timeout_seconds=900,population_application=False,
            automatic_retry=False,source_review_seal=m.REVIEW_SHA)
        lines=['ANNOTATION: "'+m.ANNOTATION+'"']
        for i in cls.instances:
            lines+=['CHECKSUM: "%s %s"'%(i['design_module_checksum'],i['toggle_checksum']),'INSTANCE: '+i['scope']]
            lines+=['Toggle %s "logic %s%s"'%(n['name'],m.bounds(n),n['name']) for n in i['targets']]
        cls.el='\n'.join(lines)+'\n'
        cls.rows=[[str(k+1),n['name']+m.bounds(n),n['name']+m.bounds(n),n['name']+m.bounds(n),'0']
                  for k,n in enumerate(cls.instances[0]['targets']+cls.instances[0]['protected'])]

    def inv(self,rows,stage='before'):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with (out/('native_%s_0.tsv'%stage)).open('w',newline='') as f:
                w=csv.writer(f,delimiter='\t');w.writerow(['handle','path','meta','name','excluded']);w.writerows(rows)
            return m.inventory(out,self.c,stage,0)

    def reject(self,text):
        with self.assertRaises(ValueError):m.parse_el(text,self.c)

    def test_exact108_capacity_and746_complement(self):
        m.contract(self.c);self.assertEqual(len(m.parse_el(self.el,self.c)),108)
        self.assertEqual(sum(n['logical_bits'] for i in self.instances for n in i['targets']),2628)
        self.assertEqual(len(self.inv(self.rows)),746)
        self.assertEqual([len(i['protected']) for i in self.instances],[719]*4)

    def test_full_other_fields_read_data_and_write_ports_present(self):
        protected=self.instances[0]['protected'];names={n['name'] for n in protected}
        for n in ('operand_payload[0].addr','operand_payload[0].opqueue','operand_payload[9].wdata',
                  'vrf_wdata_o','vrf_be_o','rst_ni','operand_queue_cmd_valid_o'):
            self.assertIn(n,names)

    def test_scope_checksum_annotation_drift(self):
        for old,new in ((self.instances[0]['scope'],'wrong.scope'),('553408029','553408028'),(m.ANNOTATION,'other')):
            self.reject(self.el.replace(old,new,1))

    def test_width_and_field_drift(self):
        self.reject(self.el.replace('[63:0]operand_payload[0].wdata','[62:0]operand_payload[0].wdata',1))
        self.reject(self.el.replace('operand_payload[0].wdata','operand_payload[0].addr',1))

    def test_no_whole_requester_or_payload_other_metric(self):
        for line in ('Toggle operand_payload "logic operand_payload"','Branch 1','Line 1','INSTANCE: other'):
            self.reject(self.el+line+'\n')

    def test_missing_duplicate_and_one_direction(self):
        lines=self.el.splitlines();self.reject('\n'.join(lines[:-1]));self.reject(self.el+lines[-1]+'\n')
        self.reject(self.el.replace('Toggle operand_payload[0].wen','Toggle 0to1 operand_payload[0].wen',1))

    def test_both_scalar_directions_and_order_independence(self):
        paired=[]
        for line in self.el.splitlines():
            if line.startswith('Toggle ') and '.wen "' in line:
                paired.extend([line.replace('Toggle ','Toggle 1to0 ',1),line.replace('Toggle ','Toggle 0to1 ',1)])
            else:paired.append(line)
        self.assertEqual(m.parse_el('\n'.join(paired),self.c),m.parse_el(self.el,self.c))

    def test_extra_missing_native_and_metadata(self):
        for rows in (self.rows+[self.rows[0]],self.rows[:-1]):
            with self.assertRaises(ValueError):self.inv(rows)
        rows=copy.deepcopy(self.rows);rows[0][2]='logic wrong_name'
        with self.assertRaises(ValueError):self.inv(rows)

    def test_all_five_stage_excluded_flags(self):
        for stage in m.STAGES:
            rows=copy.deepcopy(self.rows)
            if stage in ('selected','reloaded'):
                for r in rows[:27]:r[4]='1'
            self.assertEqual(len(self.inv(rows,stage)),746)
            rows[-1][4]='1'
            with self.assertRaises(ValueError):self.inv(rows,stage)

    def test_unknown_excluded_flag(self):
        rows=copy.deepcopy(self.rows);rows[0][4]='X'
        with self.assertRaises(ValueError):self.inv(rows)

    def test_missing_selected_target(self):
        with self.assertRaises(ValueError):self.inv(self.rows,'selected')

    def test_pin_drift_and_global_empty(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);p=out/'final-empty.el';p.write_bytes(b'');m.check_file(out,self.c,p.name)
            pins={str(p):m.life.digest(p)};p.write_bytes(b'// not empty')
            with self.assertRaises(ValueError):m.life.check(pins)
            with self.assertRaises(ValueError):m.check_file(out,self.c,p.name)

    def test_source_contract_mutation_no_broadening(self):
        c=copy.deepcopy(self.c);c['instances'][0]['targets'][0]['name']='operand_payload'
        with self.assertRaises(ValueError):m.contract(c)

    def test_actual_rooted_percent_encoding(self):
        count=0
        for name in ('qbs-cause9-constant13-native-agent-20261007-01',
                     'csr-reserved1193-native-agent-20261007-02'):
            with (m.life.OUT/name/'rooted_before.csv').open(newline='') as f:
                for row in csv.DictReader(f):
                    for metric in ('Score','Line','Toggle','FSM','Condition','Branch'):
                        m.strict_percent(row[metric]);count+=1
        self.assertGreaterEqual(count,24)
        self.assertEqual(m.strict_percent('17.94%'),17.94)
        self.assertIsNone(m.strict_percent('NA'))

    def test_percent_malformed_rejected(self):
        for value in ('17.94%%','17.94%extra','17.94',' 17.94%','17.94% ',
                      '+17.94%','NaN%','-1%','100.01%','101%','inf%','0x10%',17.94,None):
            with self.subTest(value=value),self.assertRaises(ValueError):m.strict_percent(value)

    def test_complete_Tcl_body_four_scopes_five_stages_flags(self):
        t=tkinter.Tcl();t.eval('set ::read108_test_only 1')
        t.eval('source {%s}'%(m.HERE/'qualify_requester_read108_native.tcl'))
        for command in ('lassign','dict'):
            if t.eval('info commands '+command):t.eval('rename '+command+' {}')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);t.setvar('env(DVE_COVERAGE_OUTPUT)',d)
            vals=dict(fma_design='HOST_ONLY',fma_vdb='HOST_ONLY',fma_test='HOST_ONLY',fma_python='HOST_ONLY',
                      fma_helper='HOST_ONLY',qfp_primitives=str(m.HERE/'fma_datapath_native.tcl'))
            lines=['set %s {%s}\n'%x for x in vals.items()]+['set fma_instances {}\n']
            for idx,i in enumerate(self.instances):
                labels=[n['name']+m.bounds(n) for n in i['targets']+i['protected']]
                t.setvar('labels_%d'%idx,t.call('list',*labels))
                lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n'%(i['scope'],
                    ' '.join(n['name']+m.bounds(n) for n in i['targets']),' '.join(n['name']+m.bounds(n) for n in i['protected']),idx))
            (out/'selection.tcl').write_text(''.join(lines))
            t.eval('''
set selected {};set excluded {};set saved {};set saves {};set chosen {};set active 0
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_list_action {args} {
    set scope [lindex $args end];set n 0
    foreach i $::fma_instances {if {[lindex $i 0] eq $scope} {set ::active $n;return};incr n}
    error "Unapproved scope"
}
proc gui_list_get {args} {
    set op [lindex $args 2];set n [lindex $args end];set labels [set ::labels_$::active]
    if {$op eq "-firstChild"} {if {[llength $args]==3} {return 1};return 0}
    if {$op eq "-nextSibling"} {if {$n<[llength $labels]} {return [expr {$n+1}]};return 0}
    return [lindex $labels [expr {$n-1}]]
}
proc gui_list_get_selected {args} {
    if {[lindex $args end] eq "-count"} {return [llength $::selected]};return $::selected
}
proc gui_list_select {args} {
    if {[lindex $args 2] eq "-unselect"} {set ::selected {};return}
    set ::selected [lindex $args 3]
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {set ::excluded {};return}
    if {[lsearch -exact $args -excluded]>=0} {
        set key [list $::active [lindex $::selected 0]]
        return [expr {[lsearch -exact $::excluded $key]>=0}]
    }
}
proc gui_exclude_items {args} {
    if {[llength $::selected]!=1} {error "Bad selection"}
    set key [list $::active [lindex $::selected 0]]
    lappend ::chosen $key;lappend ::excluded $key
}
proc gui_exclusion_file {args} {
    set name [file tail [lindex [lindex $args end] 0]]
    if {[lindex $args 0] eq "-save"} {
        lappend ::saves $name
        if {$name eq "first.el"} {set ::saved $::excluded}
    } else {
        if {$name ne "first.el"} {error "Wrong reload"};set ::excluded $::saved
    }
}
rename exec real_exec
proc exec {args} {return HOST_MODEL_CHECK}
qfp_session
''')
            self.assertEqual(t.eval('llength $chosen'),'108')
            self.assertEqual(t.eval('llength $excluded'),'0')
            self.assertEqual(t.splitlist(t.eval('set saves')),('initial-empty.el','first.el','reset-empty.el','second.el','final-empty.el'))
            for index in range(4):
                before=m.inventory(out,self.c,'before',index)
                for stage in m.STAGES[1:]:self.assertEqual(m.inventory(out,self.c,stage,index),before)


if __name__=='__main__':unittest.main()
