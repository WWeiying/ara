import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import rvh_nine_policy_runtime as n

OUT=n.frozen.OUT
EIGHT=OUT/'lzc-snapshot-eight-policy-runtime-727-agent-20261006-01'
EIGHT_SEAL='130d0f172075031b879bcdd1ae9a87bc070805da87c61cee3ddcc83818c49b97'
REVIEW=OUT/'rvh-full247-native-el-review-727-20261006-01'
REVIEW_SEAL='c315cf9d7396cac87614019a28d1e05941f4b40ec0476f14e2b0b4b52af9b3f3'


class NineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delegate=patch.object(n.eight,'split_bind',return_value={})
        cls.delegate.start();cls.addClassCleanup(cls.delegate.stop)
        cls.contract=n.build_contract(EIGHT,EIGHT_SEAL,REVIEW,REVIEW_SEAL)
        cls.capture=n.capture_config(cls.contract)
        cls.first=(REVIEW/'limited-native-247.el').read_bytes()
        cls.second=(Path(cls.capture['output'])/'second.el').read_bytes()
        cls.original=(EIGHT/'combined-eight.el').read_bytes()

    def test_actual_latest_contract_exact_counts(self):
        c=self.contract
        self.assertEqual((c['population'],c['targets'],c['protected'],c['audited']),
                         (727,6139,19307,25446))
        self.assertEqual(c['state_checks'],152676)
        self.assertEqual(len(c['native_rows']),1780)
        self.assertEqual(sum(r[4] for r in c['native_rows']),247)
        self.assertFalse(c['application_approval']);self.assertFalse(c['launch_supported'])

    def test_actual_reordered_rvh_signature_not_whole_byte(self):
        self.assertNotEqual(self.first,self.second)
        self.assertTrue(n.roundtrip(self.original+self.first,self.second+self.original,self.contract))

    def test_unknown_scope_checksum_metric_rejected(self):
        for raw in (self.first.replace(b'i_ariane',b'i_injected'),
                    self.first.replace(b'1976186923',b'1976186924'),
                    self.first.replace(b'Branch 3 ',b'Condition 3 ',1)):
            with self.subTest(raw=raw[:90]),self.assertRaises(ValueError):
                n.partition(self.original+raw,self.contract)

    def test_duplicate_rvh_record_rejected(self):
        block=n.eight.metric.blocks(self.first)[0][1]
        with self.assertRaises(ValueError):n.partition(self.original+self.first+block,self.contract)

    def test_original_eight_byte_order_still_required(self):
        blocks=n.eight.metric.blocks(self.original)
        altered=b''.join(c for _,c in reversed(blocks))
        # Isolate the original byte-order boundary from semantic record validation.
        with patch.object(n,'partition',return_value={}):
            with self.assertRaisesRegex(ValueError,'eight export bytes'):
                n.roundtrip(self.original+self.first,altered+self.second,self.contract)

    def test_fragment_drops_only_exact_owned_rvh(self):
        self.assertEqual(n.eight_fragment(self.first+self.original,self.contract),self.original)

    def test_generate_annotation_preserved_strictly(self):
        bad=self.first.replace(b'vcs_gen_start:i=0:vcs_gen_end:',b'vcs_gen_start:i=1:vcs_gen_end:',1)
        with self.assertRaises(ValueError):n.partition(self.original+bad,self.contract)

    def test_parent_aggregate_allowed_protected_leaf_not_allowed(self):
        active=self.contract['rvh_target_scopes']
        base='ara_tb.dut.i_ara_soc.i_system'
        self.assertTrue(n.branch_change_allowed(base+'.i_ariane.ex_stage_i','Branch',active))
        self.assertFalse(n.branch_change_allowed(base+'.i_ara','Branch',active))
        self.assertFalse(n.branch_change_allowed(base+'.i_ariane','Condition',active))
        self.assertFalse(n.branch_change_allowed(base+'.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_dtlb','Branch',active))

    def test_actual_after_root_active_and_six_stages(self):
        root=Path(self.capture['output'])
        for stage in n.STAGES:
            f=root/('states_'+('reloaded' if stage=='after-root' else stage)+'.tsv')
            self.assertEqual(len(n.audit_states(f,self.contract,stage)),1780)

    def test_audit_extra_missing_duplicate_identity_and_nonboolean(self):
        c=self.contract
        expected={(r[0],'branch',r[1]):(r[2],r[3]) for r in c['native_rows']}
        targets={(r[0],'branch',r[1]) for r in c['native_rows'] if r[4]}
        with (Path(self.capture['output'])/'states_before.tsv').open(newline='') as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        for altered in (rows[:-1],rows+[rows[0]],
                        [dict(rows[0],excluded='2')]+rows[1:],
                        [dict(rows[0],meta='Branch999.0')]+rows[1:]):
            with self.assertRaises(ValueError):n.audit_rows(altered,expected,targets,False)
        guarded=next(i for i,r in enumerate(rows) if (r['scope'],r['metric'],r['coordinate']) not in targets)
        altered=copy.deepcopy(rows);altered[guarded]['excluded']='1'
        with self.assertRaises(ValueError):n.audit_rows(altered,expected,targets,False)

    def test_library_is_exact_frozen_prefix_not_main(self):
        library=n.eight_library()
        self.assertEqual(n.eight.TCL.read_text().split('set failed [catch {eight_initialize; qbsapp_session} message]\n')[0],library)
        self.assertNotIn('gui_exit',library)

    def test_verifier_adapts_only_one_original_byte_comparison(self):
        result=n.adapted_eight_verifier(lambda p,s:None)
        self.assertIn('Actual combined reload differs',result.__code__.co_consts)
        self.assertIsNot(result,n.eight.verify)

    def test_private_payload_and_sealed_callback(self):
        with self.assertRaises(ValueError):n.selection_payload(self.contract,'mutable')
        payload=n.selection_payload(self.contract,'a'*64)
        self.assertIn('namespace eval rvh9',payload)
        self.assertNotIn('dbg_scopes',payload);self.assertNotIn('dbg_select',payload)
        self.assertIn('variable python',payload)

    def test_tcl_selector_empty_token_only_and_legacy_untouched(self):
        mock=r'''
set nine_library_only 1
proc lpd_require {ok message} {if {!$ok} {error $message}}
proc dbg_select {args} {return LEGACY}
set dbg_scopes {unchanged}
set selected [list {}]
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
'''
        checks=r'''
rvh9::select MISSING_DEFAULT2.3
if {$selected ne "MISSING_DEFAULT2.3"} {error selection}
foreach bad {{evil} {Branch0.1 Branch0.1} {BranchX.1}} {
    if {![catch {rvh9::selection $bad}]} {error invalid-accepted}
}
if {[dbg_select] ne "LEGACY" || $dbg_scopes ne "unchanged"} {error legacy-mutated}
puts RVH9_PRIVATE_PASS
'''
        r=subprocess.run(['tclsh'],input=mock+n.TCL.read_text()+checks,text=True,capture_output=True,timeout=5)
        self.assertEqual(r.stderr,'');self.assertIn('RVH9_PRIVATE_PASS',r.stdout)

    def test_tcl_complete_before_and_after_root_audit_gate(self):
        mock=r'''
set nine_library_only 1
proc lpd_require {ok message} {if {!$ok} {error $message}}
proc seven_replace_once {body old new} {
    if {[string first $old $body]<0 || [string first $old $body]!=[string last $old $body]} {error boundary}
    return [string map [list $old $new] $body]
}
proc source {path} {
    if {[file tail $path] eq "rvh9-selection.tcl"} {
        set ::rvh9::scopes {}
        for {set i 0} {$i<14} {incr i} {
            lappend ::rvh9::scopes scope$i
            if {$i==0} {set num 1780} else {set num 0}
            set ::rvh9::keys(scope$i) {};set ::rvh9::targets(scope$i) {}
            for {set j 0} {$j<$num} {incr j} {
                lappend ::rvh9::keys(scope$i) $j
                if {$j<247} {lappend ::rvh9::targets(scope$i) $j}
            }
        }
    }
}
proc eight_initialize {} {
    proc qbs_audit {stage active} {lappend ::old_stages $stage}
    proc seven_load {path} {set ::loaded $path}
    proc qbsapp_session {} {
        set path combined-eight.el
        lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq
        [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]}] "Combined EL actual reload bytes differ"
        puts EIGHT_ACTUAL_RELOAD_EXACT5892
    }
}
set env(DVE_COVERAGE_OUTPUT) /unused
set old_stages {};set new_stages {};set bad_before 1
'''
        checks=r'''
nine_initialize
proc rvh9::audit {stage active} {
    if {$stage eq "before" && $::bad_before} {error protected-failure}
    lappend ::new_stages $stage
}
if {![catch {seven_load forbidden.el}]} {error early-load}
if {![catch {qbs_audit before 0}]} {error missing-protection-failure}
if {$::rvh9::before_complete} {error opened-on-failure}
set bad_before 0
foreach stage {before selected reset reloaded after-root final} {
    qbs_audit $stage [expr {$stage eq "selected" || $stage eq "reloaded" || $stage eq "after-root"}]
}
seven_load combined-nine.el
if {$loaded ne "combined-nine.el" || [llength $new_stages]!=6} {error incomplete}
if {[string first check-roundtrip [info body qbsapp_session]]<0} {error byte-gate-not-replaced}
puts RVH9_COMPLETE_GATE_PASS
'''
        r=subprocess.run(['tclsh'],input=mock+n.TCL.read_text()+checks,text=True,capture_output=True,timeout=5)
        self.assertEqual(r.stderr,'');self.assertIn('RVH9_COMPLETE_GATE_PASS',r.stdout)
        self.assertEqual(r.stdout.count('NINE_FULL_AUDIT'),6)


if __name__=='__main__':unittest.main()
