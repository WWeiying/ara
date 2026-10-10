import json
import subprocess
import unittest
from unittest.mock import patch

import lzc_snapshot_eight_policy_runtime as e

B=b'CHECKSUM: "1 2"\nINSTANCE: dut.i_requester\nBranch 0 "3" "expr" (0) "expr 0"\n'
C=b'CHECKSUM: "1 4"\nINSTANCE: dut.i_requester\nCondition 1 "5" "replay 1 -1" (2 "1")\n'
L=b'CHECKSUM: "6 7"\nINSTANCE: dut.i_lzc\nCondition 2 "8" "sel 1 -1" (2 "1")\n'


class EightRuntimeTests(unittest.TestCase):
    def test_approved_scope_only_fix_exact(self):e.scope_fix()

    def test_scope_fix_drift_reject(self):
        with patch.object(e.frozen,'sha',return_value='wrong'):
            with self.assertRaises(ValueError):e.scope_fix()

    def test_same_scope_metric_dispatch_and_reorder(self):
        sources=dict(six=B,lzc=L,snapshot=C)
        self.assertEqual(e.route(C+B+L,sources),sources)

    def test_unknown_scope_type_checksum_mixed_reject(self):
        sources=dict(six=B,lzc=L,snapshot=C)
        for c in (C.replace(b'1 4',b'1 2'),C.replace(b'dut.i_requester',b'evil.i_requester'),
                  C.replace(b'Condition',b'Toggle'),C+B.split(b'INSTANCE:')[1]):
            with self.subTest(c=c),self.assertRaises(ValueError):e.route(B+L+c,sources)

    def test_condition_extra_rejected_by_semantic_binding(self):
        sources=dict(six=B,lzc=L,snapshot=C)
        with self.assertRaises(ValueError):e.split_bind(B+L+C+C,{},sources,[])

    def test_original_four_scopes_share_branch_owner(self):
        c=json.loads((e.mask.CURRENT_SIX).read_bytes())
        native=e.mask.parse_records(e.MASK_EL.read_text())
        self.assertEqual(len(native),24)
        self.assertTrue(all(c['scope_owners'][r['scope']]=='debug' for r in native))

    def test_prepare_has_no_process_launch(self):
        import inspect
        s=inspect.getsource(e.prepare)
        self.assertNotIn('Popen',s);self.assertNotIn('subprocess.run',s)

    def test_lzc_snapshot_cross_protection_overlap_rejected(self):
        review=dict(exact_protection_rows=[dict(scope='dut.shared')],candidates=[])
        plan=dict(source_proof=str(e.SOURCE_PROOF/'review.json'),source_proof_sha256=e.seven.PROOF_SEAL,
                  exact_lzc_protection_rows=review['exact_protection_rows'],condition_native_records=[])
        with patch.object(e.frozen,'load_sealed',return_value=review):
            with self.assertRaises(ValueError):
                e.lzc_binding(plan,{}, {},dict(preserved_protected=[dict(scope='dut.shared')]))

    def test_lzc_protection_inventory_omission_rejected(self):
        review=dict(exact_protection_rows=[dict(scope='dut.lzc')],candidates=[])
        plan=dict(source_proof=str(e.SOURCE_PROOF/'review.json'),source_proof_sha256=e.seven.PROOF_SEAL,
                  exact_lzc_protection_rows=[],condition_native_records=[])
        with patch.object(e.frozen,'load_sealed',return_value=review):
            with self.assertRaises(ValueError):e.lzc_binding(plan,{}, {},dict(preserved_protected=[]))

    def test_actual_full_native_proposal_metric_dispatch(self):
        sources=dict(six=(e.mask.CURRENT_SIX.parent/'combined.el').read_bytes(),
            lzc=(e.SOURCE_PROOF/'candidate60.el').read_bytes(),snapshot=e.MASK_EL.read_bytes())
        self.assertEqual(e.route(b''.join(sources.values()),sources),sources)
        self.assertEqual(e.metric.split_exact(b''.join(sources.values()),sources),sources)

    def test_tcl_global_groups_and_full_before_gate(self):
        body=e.TCL.read_text().split('proc eight_snapshot_audit',1)[1]
        body='proc eight_snapshot_audit'+body.split('set failed [catch {eight_initialize;',1)[0]
        mock=r'''
proc lpd_require {ok message} {if {!$ok} {error $message}}
proc seven_replace_once {body old new} {
    if {[llength [split $body $old]]<2} {error missing}
    return [string map [list $old $new] $body]
}
proc source {path} {
    if {[file tail $path] eq "snapshot-selection.tcl"} {
        upvar 1 lzc_batch_groups rows
        set rows {}
        for {set i 0} {$i<36} {incr i} {
            if {$i<24} {set names {01 10 11};set targets {01}} else {set names {01 10};set targets {}}
            lappend rows [list scope expression $names $targets {}]
        }
    }
}
proc seven_initialize {} {
    proc qbs_audit {stage active} {lappend ::seen six-$stage}
    proc seven_load {path} {set ::loaded $path}
    proc qbsapp_session {} {set path combined-seven.el;puts SEVEN_ACTUAL_RELOAD_EXACT5868}
}
set env(DVE_COVERAGE_OUTPUT) /unused
set seen {}
'''
        checks=r'''
eight_initialize
proc eight_snapshot_audit {stage active} {lappend ::seen snapshot-$stage}
if {![catch {seven_load blocked.el}]} {error early-load}
if {[llength $::lzc_batch_groups]!=36} {error missing-global}
foreach stage {before selected reset reloaded after-root final} {
    qbs_audit $stage [expr {$stage eq "selected" || $stage eq "reloaded" || $stage eq "after-root"}]
}
seven_load combined-eight.el
if {$loaded ne "combined-eight.el" || [llength $seen]!=12} {error incomplete}
puts MOCK_EXACT_PASS
'''
        result=subprocess.run(['tclsh'],input=mock+body+checks,text=True,capture_output=True,timeout=5)
        self.assertEqual(result.stderr,'')
        self.assertIn('MOCK_EXACT_PASS',result.stdout)
        self.assertEqual(result.stdout.count('EIGHT_FULL_AUDIT'),6)


if __name__=='__main__':unittest.main()
