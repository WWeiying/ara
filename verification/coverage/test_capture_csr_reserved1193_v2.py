import copy
import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_csr_reserved1193_v2 as m


class Membership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=m.life.read_bound(m.ORIGIN/'config.json',m.ORIGIN_SHA)
        cls.c.update(membership_authority=m.AUTHORITY,origin_config_sha=m.ORIGIN_SHA,
                     protected_objects=2031,protected_target_bits=111,per_bit_GUI_flags_read=False)
        cls.text=m.original.candidate(cls.c)

    def test_actual_frozen_source_compiled_complete_complements(self):
        m.contract(self.c)
        self.assertEqual(len(m.records(self.text,self.c)),2386)
        self.assertEqual(sum(len(t['retained_source_bits']) for t in self.c['targets']),111)

    def test_widen_into_retained_bit_rejects(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('Toggle dcache_q [1]','Toggle dcache_q [1:0]'),self.c)

    def test_extra_field_port_array_or_scope_rejects(self):
        for line in ['Toggle clk_i "logic clk_i"','Toggle mscratch_q "logic mscratch_q[63:0]"',
                     'Toggle pmpaddr_o "logic [0:0][53:0]pmpaddr_o"',
                     'INSTANCE: other','CHECKSUM: "1371260681 1176918775"']:
            with self.assertRaises(ValueError):m.records(self.text+line+'\n',self.c)

    def test_missing_direction_rejects(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('Toggle dcache_q [1]','Toggle 0to1 dcache_q [1]'),self.c)

    def test_cross_bit_duplicates_rejects(self):
        with self.assertRaises(ValueError):m.records(self.text+'Toggle 1to0 dcache_q [2:1] "logic dcache_q[63:0]"\n',self.c)

    def test_checksum_or_full_declaration_rejects(self):
        for old,new in [('1176918775','1176918776'),('logic dcache_q[63:0]','logic dcache_q[62:0]')]:
            with self.assertRaises(ValueError):m.records(self.text.replace(old,new),self.c)

    def test_order_only_changes_do_not_change_membership(self):
        lines=self.text.splitlines()
        reordered='\n'.join(lines[:3]+list(reversed(lines[3:])))+'\n'
        self.assertEqual(m.records(self.text,self.c),m.records(reordered,self.c))

    def test_actual_full_inventory_non_target_flags_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            raw=(m.ORIGIN/'objects-before.tsv').read_text()
            (out/'objects-before.tsv').write_text(raw)
            self.assertEqual(len(m.inventory(out,self.c,'before')),2077)
            with (m.ORIGIN/'objects-before.tsv').open() as f:rows=list(csv.reader(f,delimiter='\t'))
            targets={m.original.declaration(n) for n in self.c['nodes'] if n['name'] in m.original.expected_bits()}
            for row in rows[1:]:
                if row[2] in targets:row[3]='1'
            def write():
                with (out/'objects-selected.tsv').open('w',newline='') as f:csv.writer(f,delimiter='\t').writerows(rows)
            write();self.assertEqual(len(m.inventory(out,self.c,'selected')),2077)
            row=next(r for r in rows[1:] if r[2]=='clk_i');row[3]='1';write()
            with self.assertRaisesRegex(ValueError,'Protected'):m.inventory(out,self.c,'selected')

    def test_five_el_state_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for stage,file in m.EL_FILES.items():
                (out/file).write_text(self.text if stage in ('selected','reloaded') else '')
                self.assertEqual(len(m.el(out,self.c,stage)),2386 if stage in ('selected','reloaded') else 0)
            (out/'final-empty.el').write_text('\n')
            with self.assertRaises(ValueError):m.el(out,self.c,'final')


class NativeMetrics(unittest.TestCase):
    def fixture(self):
        raw=dict(Score='50.00',Line='70.00',Toggle='40.00',FSM='NA',Condition='60.00',Branch='30.00')
        applied=dict(raw,Toggle='45.00',Score='51.00')
        return dict(before=raw,selected=applied,reset=dict(raw),reloaded=dict(applied),final=dict(raw))

    def test_measured_application_and_restoration(self):m.compare_metrics(self.fixture())

    def test_loaded_only_or_reset_or_other_metric_drift_rejects(self):
        for stage,metric,value in [('selected','Toggle','40.00'),('final','Toggle','41.00'),
                                   ('reloaded','Score','51.01'),('selected','Line','71.00')]:
            values=self.fixture();values[stage]=dict(values[stage],**{metric:value})
            with self.assertRaises(ValueError):m.compare_metrics(values)


class FullTclEntry(unittest.TestCase):
    def test_exact_five_stages_rooted_contract_no_bit_gui_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            (out/'selection.tcl').write_text('''set ::fma_design design
set ::fma_vdb vdb
set ::fma_test test
set ::csr_scope ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i
set ::csr_python python
set ::csr2_helper helper
set ::p740_scopes [list $::csr_scope]
set ::p740_root_names($::csr_scope) csr_regfile_i
''')
            (out/'candidate.el').write_text('EXACT_NATIVE_BITS\n')
            script='set ::csr2_test_only 1\nsource {'+str(m.HOOK)+'}\n'
            script+='set ::env(DVE_COVERAGE_OUTPUT) {'+tmp+'}\n'
            script+='''
set ::active 0;set ::root ara_tb
array set ::selected {CovDetail.1 {} CoverageTable.1 {}}
proc gui_open_cov {args} {}
proc gui_covtable_show {args} {}
proc gui_covtable_setroot {args} {set ::root [lindex $args end]}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_list_expand {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_cov_tgl_double_click {args} {error "No bit pane guessing"}
proc gui_cov_tgl_compress {args} {error "No bit pane guessing"}
proc gui_list_get_selected {args} {
    set id [lindex $args 1]
    if {[lsearch $args -count]>=0} {return [llength $::selected($id)]}
    return [list $::selected($id)]
}
proc gui_list_select {args} {
    set id [lindex $args 1]
    if {[lsearch $args -unselect]>=0} {set ::selected($id) {};return}
    set ::selected($id) [lindex $args end]
}
proc gui_list_get_property {args} {
    return [lindex {Score Line Toggle FSM Condition Branch} [expr {[lindex $args end]-5}]]
}
proc gui_list_get {args} {
    set id [lindex $args 1];set flag [lindex $args 2]
    if {$flag eq "-firstChild"} {if {[llength $args]==3} {return 1};return 0}
    if {$flag eq "-nextSibling"} {return 0}
    if {$id eq "CovDetail.1"} {return {dcache_q[63:0]}}
    if {$flag eq "-text" && [lindex $args 3]>=5} {
        set col [lindex $args 3]
        if {$col==5} {return [expr {$::active?51.0:50.0}]}
        if {$col==7} {return [expr {$::active?45.0:40.0}]}
        return 60.0
    }
    if {$::root eq "ara_tb"} {return ara_tb}
    return csr_regfile_i
}
proc gui_exclusion {args} {
    if {[lsearch $args -reset]>=0} {set ::active 0;return}
    if {[lsearch $args -tgl_transition]>=0} {error "No per-bit flag claim"}
    if {[lsearch $args -recalculate]>=0} {return}
    return $::active
}
proc gui_exclusion_file {args} {
    set file [lindex [lindex $args end] 0]
    if {[lsearch $args -load]>=0} {set ::active 1;return}
    set f [open $file w];if {$::active} {puts $f EXACT_NATIVE_BITS};close $f
}
rename exec real_exec
proc exec {args} {return MOCK_STRICT_HOST_GATE}
csr2_session
if {$::active} {error "Final reset missing"}
puts FULL_FIVE_STAGE_PASS
'''
            result=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} msg]} {puts stderr $msg;puts stderr $::errorInfo;exit 1}\n',text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            c=dict(scope='ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i')
            m.compare_metrics({stage:m.metrics(out,c,stage) for stage in m.STAGES})
            self.assertEqual((out/'first.el').read_bytes(),(out/'second.el').read_bytes())
            for stage in ('before','reset','final'):self.assertEqual((out/m.EL_FILES[stage]).read_bytes(),b'')


if __name__=='__main__':unittest.main()
