import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import fpnew_class_padding_local as p


def fixture():
    return dict(instances=[dict(scope='a.slice',design_module_checksum='1',toggle_checksum='2',
        signals=[dict(name='slice_class_result',left=31,right=0,bits=list(range(10,32)))])])


class NativeMembership(unittest.TestCase):
    def test_actual_prepare_full_sealed_source_template_and_check(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p.life,'OUT',Path(tmp)):
            out=Path(tmp)/'prepared'
            p.prepare(out)
            c=p.check(out,p.life.digest(out/'config.json'))
            self.assertEqual(len(p.records((out/'candidate.el').read_text(),c)),5316)
            self.assertEqual(c['raw_serialized_mapping_calibrated'],False)
            self.assertFalse((out/'execution.json').exists())

    def test_complete_both_directions(self):
        c=fixture();self.assertEqual(p.records(p.candidate(c),c),p.wanted(c))

    def test_dynamic_low_bit_rejected(self):
        c=fixture();text=p.candidate(c).replace('[10] "logic','[9] "logic',1)
        with self.assertRaises(ValueError):p.records(text,c)

    def test_missing_direction(self):
        c=fixture();text='\n'.join(p.candidate(c).splitlines()[:-1])+'\n'
        with self.assertRaises(ValueError):p.records(text,c)

    def test_duplicate_and_cross_range(self):
        c=fixture();text=p.candidate(c)
        for bad in (text+text.splitlines()[3]+'\n',text.replace('[10] "logic','[11:9] "logic',1)):
            with self.assertRaises(ValueError):p.records(bad,c)

    def test_foreign_field_checksum_and_whole_object(self):
        c=fixture();text=p.candidate(c)
        for bad in (text.replace('"1 2"','"1 3"'),text.replace('INSTANCE: a.slice','INSTANCE: foreign'),
                    text.replace('slice_class_result','result_o'),text.replace(' [10]','',1)):
            with self.assertRaises(ValueError):p.records(bad,c)

    def test_annotation_and_signature(self):
        c=fixture();text=p.candidate(c)
        for bad in (text.replace(p.NOTE,'foreign'),text.replace('[31:0]','[30:0]',1)):
            with self.assertRaises(ValueError):p.records(bad,c)

    def test_actual_source_full_logical_membership_and_complements(self):
        q=p.life.read_bound(p.SOURCE,p.SOURCE_SHA)
        instances={}
        for r in q['candidates']:
            i=instances.setdefault(r['scope'],dict(scope=r['scope'],design_module_checksum=r['module_checksum'],
                toggle_checksum=r['toggle_checksum'],signals=[],parameters=r['parameters']))
            a=r['attributes'];i['signals'].append(dict(name=r['field'],left=int(a['left']),right=int(a['right']),
                bits=r['logical_bits'],protected_bits=r['protected_bits']))
        c=dict(instances=list(instances.values()),schema='FPNEW_CLASS_PADDING783_LOCAL_PREPARED',
            source_sha=p.SOURCE_SHA,population_application=False,raw_serialized_mapping_calibrated=False)
        p.contract(c);self.assertEqual(len(p.records(p.candidate(c),c)),5316)
        bad=copy.deepcopy(c);bad['instances'][0]['signals'][0]['bits'].append(0)
        with self.assertRaises(ValueError):p.contract(bad)


class TclEntry(unittest.TestCase):
    def exercise(self, bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'candidate.el').write_text('EXACT_PARTIAL\n')
            (root/'selection.tcl').write_text('''set ::mq_design {frozen}
set ::mq_vdb {sample}
set ::mq_test {selected}
set ::mq_instances [list [list {a.slice} [list {slice_class_result[31:0]}]]]
''')
            script='''
set cp_test_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set active 0
set selected {}
set seen {}
proc p740_root {} {}
proc p740_select {scope} {return $scope}
proc gui_open_cov {args} {}
proc gui_list_action {args} {}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
 if {[lindex $args 2] eq "-unselect"} {set ::selected {};return}
 set ::selected [lindex $args 3]
}
proc gui_exclusion {args} {return 0}
proc mq_load {name} {set ::active 1}
proc qc_reset {} {set ::active 0}
proc qc_save {name} {
 set f [open [file join $::env(DVE_COVERAGE_OUTPUT) $name] w]
 if {$::active} {puts $f EXACT_PARTIAL}
 close $f
}
proc mq_audit {stage flags} {
 set f [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_0.tsv] w]
 puts $f "handle\\tpath\\tmeta\\tname\\ttype\\tcoverage\\tdisplay"
 puts $f "1\\tItem1\\tItem1\\tslice_class_result[31:0]\\tsignal\\t0%%\\t0%%"
 close $f
}
proc cp_gate {stage} {
 lappend ::seen $stage
 if {$::bad && $stage eq "reloaded"} {error "intentional exact reload rejection"}
}
set bad %d
if {[catch {cp_session} message]} {puts stderr $message;exit 1}
if {$seen ne "before applied reset reloaded final"} {error "incomplete pipeline"}
puts HOST_FULL_ENTRY_PASS
'''%(p.HOOK,root,int(bad))
            # Brackets in a displayed native name must be literal Tcl data.
            script=script.replace('slice_class_result[31:0]\\t','slice_class_result\\[31:0\\]\\t')
            result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=10)
            return result

    def test_actual_sourced_entry_proc_selection_five_stages(self):
        r=self.exercise();self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('HOST_FULL_ENTRY_PASS',r.stdout)

    def test_reload_failure_does_not_print_success(self):
        r=self.exercise(True);self.assertEqual(r.returncode,1)
        self.assertIn('exact reload rejection',r.stderr);self.assertNotIn('HOST_FULL_ENTRY_PASS',r.stdout)


if __name__=='__main__':unittest.main()
