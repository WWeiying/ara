import json
import unittest
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import report_population788_observers as m


class Boundary(unittest.TestCase):
    def setUp(self):
        self.proof = json.loads(m.PROOF.read_text())
        self.supplement = json.loads(m.SUPPLEMENT.read_text())

    def test_real_frozen_source_boundary(self):
        self.assertEqual(m.life.digest(m.PROOF), m.PROOF_SHA)
        self.assertEqual(m.life.digest(m.SUPPLEMENT), m.SUPPLEMENT_SHA)
        m.boundary(self.proof, self.supplement)

    def test_foreign_scope(self):
        self.supplement['exact_compiled_boundary'][1]['scope'] += '.sibling'
        with self.assertRaises(ValueError):
            m.boundary(self.proof, self.supplement)

    def test_checksum_drift(self):
        self.supplement['exact_compiled_boundary'][0]['toggle_checksum'] = '0'
        with self.assertRaises(ValueError):
            m.boundary(self.proof, self.supplement)

    def test_no_assertions(self):
        self.proof['proposed_boundary']['metrics'].append('Assert')
        with self.assertRaises(ValueError):
            m.boundary(self.proof, self.supplement)

    def test_no_output(self):
        self.proof['source_proof']['adapter_output_inout_ref'] = 1
        with self.assertRaises(ValueError):
            m.boundary(self.proof, self.supplement)

    def test_native_claim_cannot_be_inferred(self):
        self.proof['native_evidence']['prior_whole_qualified'] = True
        with self.assertRaises(ValueError):
            m.boundary(self.proof, self.supplement)


class Corpus(unittest.TestCase):
    def setUp(self):
        self.ledger = ['design'] + ['test' + str(i) for i in range(788)]
        self.bits = dict(tests=self.ledger[1:], metrics={
            k: dict.fromkeys(range(n)) for k, n in
            dict(line=1892, cond=2023, branch=2155, fsm=92).items()})

    def test_788_exact_prefix_full_shapes(self):
        m.corpus(self.ledger, self.ledger[:786], self.bits)

    def test_prefix_mutation(self):
        old = self.ledger[:786]
        old[1] = 'foreign'
        with self.assertRaises(ValueError):
            m.corpus(self.ledger, old, self.bits)

    def test_duplicate(self):
        self.ledger[-1] = self.ledger[-2]
        with self.assertRaises(ValueError):
            m.corpus(self.ledger, self.ledger[:786], self.bits)

    def test_missing_metric(self):
        del self.bits['metrics']['fsm']
        with self.assertRaises(ValueError):
            m.corpus(self.ledger, self.ledger[:786], self.bits)

    def test_same_count_foreign_bits_test(self):
        self.bits['tests'] = list(self.bits['tests'])
        self.bits['tests'][-1] = 'foreign'
        with self.assertRaises(ValueError):
            m.corpus(self.ledger, self.ledger[:786], self.bits)

    def test_same_count_reordered_bits_test(self):
        self.bits['tests'] = list(reversed(self.bits['tests']))
        with self.assertRaises(ValueError):
            m.corpus(self.ledger, self.ledger[:786], self.bits)

    def test_no_output_before_contract(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report'
            with patch.object(m, 'contract', side_effect=ValueError('binding')):
                with self.assertRaises(ValueError):
                    m.prepare_plan(out)
            self.assertFalse(out.exists())


class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        review = m.life.read_bound(m.observer.REVIEW, m.observer.REVIEW_SHA)
        cls.ob = dict(compiled_scopes=review['compiled_scopes'],
                      metric_checksums={s: [t] for s, _, t in m.IDENTITIES},
                      per_metric_checksums={s: dict(tgl=[t], line=[], cond=[], branch=[], fsm=[])
                                            for s, _, t in m.IDENTITIES})
        cls.old = (m.REPORT/'combined.el').read_text()
        chunks, current, scope = [], [], None
        for line in cls.old.splitlines():
            if line.startswith('CHECKSUM:'):
                if scope not in m.SCOPES: chunks.extend(current)
                current, scope = [line], None
            elif line.startswith('INSTANCE:'):
                scope = line.split(':',1)[1].strip(); current.append(line)
            else: current.append(line)
        if scope not in m.SCOPES: chunks.extend(current)
        for item in review['compiled_scopes']:
            t = next(t for s, _, t in m.IDENTITIES if s == item['scope'])
            chunks += ['CHECKSUM: "'+str(item['design_module_checksum'])+' '+t+'"',
                       'INSTANCE: '+item['scope']]
            for node, name, _, _, _, left, right in item['typed_inventory']:
                decl = name if node == 'node' else name+'['+left+':'+right+']'
                chunks.append('Toggle '+name+' "logic '+decl+'"')
        cls.full = '\n'.join(chunks)+'\n'

    def test_actual_full_typed86_masks_cover_inherited18516(self):
        self.assertEqual(m.padding_covered(self.old,self.ob),18516)
        m.native_gate(self.full,self.old,self.ob)

    def test_unknown_valid_checksum_object_rejected(self):
        with self.assertRaises(ValueError):
            m.native_gate(self.full+'Toggle not_a_compiled_object "logic not_a_compiled_object"\n',self.old,self.ob)

    def test_deleted_all_old_padding_not_allowed(self):
        # Even an unchanged nonobserver complement plus a valid observer header
        # cannot replace the actual full typed membership.
        truncated = self.full[:self.full.rfind('Toggle ')]
        with self.assertRaises(ValueError): m.native_gate(truncated,self.old,self.ob)

    def test_kind_and_range_mutation_rejected(self):
        for changed in (self.full.replace('"logic ', '"wire ',1),
                        self.full.replace('Toggle clk_i "logic clk_i"','Toggle clk_i [1:0] "logic clk_i"',1)):
            with self.assertRaises(ValueError): m.native_gate(changed,self.old,self.ob)

    def test_duplicate_native_directive_rejected(self):
        with self.assertRaises(ValueError):
            m.native_gate(self.full+self.full[self.full.rfind('Toggle '):],self.old,self.ob)

    def test_valid_toggle_checksum_cannot_exclude_branch(self):
        with self.assertRaisesRegex(ValueError,'another metric'):
            m.native_gate(self.full+'Branch 1\n',self.old,self.ob)

    def test_real787_status_alias_retains_all_fields(self):
        manifest = m.life.read_bound(m.CSR787/'admission-manifest.json', m.CSR787_SHA)
        p = m.CSR787/'status.json'
        value = m.life.read_bound(p, manifest['output_pins'][str(p)])
        actual = m.PopulationReader().read(p, manifest['output_pins'][str(p)], True)
        self.assertEqual({k: v for k, v in actual.items() if k != 'full_OR_metric_instances'}, value)
        self.assertEqual(actual['full_OR_metric_instances'], 6162)

    def test_wrong787_status_not_normalized(self):
        for mutation in ({'aggregate_passed': 788}, {'full_OR_instances': 6161}, {'baseline': 785},
                         {'full_OR_metric_instances': 6162}):
            value = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', coverage_admitted=True,
                         aggregate_passed=787, baseline=786, full_OR_instances=6162)
            value.update(mutation)
            with self.assertRaises(ValueError): m.status787(value)

    def test_nonobserver_native_mask_changed_rejected(self):
        old = 'CHECKSUM: "1 2"\nINSTANCE: ara_tb.functional\nToggle x [3:0] "logic x[3:0]"\n'
        changed = old.replace('[3:0]', '[4:0]')
        with self.assertRaisesRegex(ValueError, 'Nonobserver'):
            m.native_gate(changed, old, {})

    def test_unknown_scope_only_observer_rejected(self):
        text = 'CHECKSUM: "2332976182 498965595"\nINSTANCE: '+m.SCOPE+'\nScope\n'
        ob = dict(compiled_scopes=[dict(scope=m.SCOPE, design_module_checksum='2332976182')],
                  metric_checksums={m.SCOPE: ['498965595']})
        with self.assertRaises(ValueError):
            m.native_gate(text, '', ob)

    def test_real_standalone_tcl_five_stage_entry(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            root = out / 'root.tcl'
            root.write_text('proc p740_root {} {}\nproc p740_select {scope} {puts "SELECT $scope"}\n')
            selection = ('set p740_scopes [lrepeat 73 scope]\nset compact_root_helper {'+str(root)+'}\n'+
                         'set observers788_compact_library {'+str(m.stable.TCL)+'}\n'+
                         'set observers788_native_library {'+str(m.NATIVE_TCL)+'}\n'+
                         'set cv_scopes [list '+ ' '.join(m.SCOPES)+']\n'+
                         'set cv_root ara_tb.dut.i_ara_soc.i_system\nset cv_annotation {'+m.observer.ANNOTATION+'}\n')
            capacities = {m.SCOPE: dict(Line=8, Condition=0, Branch=4, FSM=0, Toggle=41),
                          m.SCOPES[1]: dict(Line=0, Condition=0, Branch=0, FSM=0, Toggle=45)}
            selection += 'array set observers788_capacity {'+' '.join(
                s+','+metric+' '+str(n) for s, values in capacities.items() for metric,n in values.items())+'}\n'
            (out/'root-selection.tcl').write_text(selection)
            (out/'summary.csv.partial').write_text('raw fixture')
            script = 'set env(DVE_COVERAGE_OUTPUT) {'+str(out)+'}\n'+r'''
proc gui_exclusion_file {args} {
    if {[lindex $args 0] eq "-save"} {
        set f [open [lindex [lindex $args 2] 0] w]; close $f
    }
}
proc gui_exclusion {args} {puts "EXCLUSION $args"}
proc gui_process_events {args} {}
proc gui_cov_excl_review {args} {return 1}
proc gui_has_metric {args} {return 1}
proc gui_exclude_items {args} {
    if {[lsearch -exact $args -recursive] >= 0} {error recursive}
    set metric [lindex $args [expr {[lsearch -exact $args -metric]+1}]]
    if {$metric ni {Line Condition Branch FSM Toggle}} {error protected}
    puts "APPLY $metric"
}
'''+ 'source {'+str(m.TCL)+'}\n'+r'''
proc compact777_summary {stage} {puts "SUMMARY $stage"}
proc cv_snapshot {stage metric index scope} {puts "SNAP $stage $metric $scope"}
apply_reviewed_waivers CoverageTable.1
'''
            wrapped = 'if {[catch {\n'+script+'\n} reason]} {puts stderr $reason; exit 1}\n'
            r = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines().count('OBSERVERS788_NATIVE_FIVE_PHASE_DONE'), 1)
            self.assertEqual([l for l in r.stdout.splitlines() if l.startswith('SUMMARY ')],
                             ['SUMMARY '+s for s in ('raw','applied','reset','reloaded','final')])
            self.assertEqual([l for l in r.stdout.splitlines() if l.startswith('APPLY ')],
                             ['APPLY Line', 'APPLY Branch', 'APPLY Toggle', 'APPLY Toggle'])
            expected = []
            for stage in m.observer.STAGES:
                for metric in m.METRICS + m.observer.PROTECTED:
                    scopes = m.SCOPES if metric in m.METRICS else ('ara_tb.dut.i_ara_soc.i_system',)
                    for s in scopes:
                        if metric in m.METRICS and capacities[s][metric] == 0: continue
                        expected.append('SNAP '+stage+' '+metric+' '+s)
            self.assertEqual([l for l in r.stdout.splitlines() if l.startswith('SNAP ')], expected)
            for stage in m.observer.STAGES:
                for metric in m.METRICS:
                    for i,s in enumerate(m.SCOPES):
                        if capacities[s][metric] == 0:
                            self.assertEqual(json.loads((out/('%s_%s_%d.skipped.json' % (stage,metric,i))).read_text()),
                                             dict(status='SKIPPED_COMPILED_ZERO',scope=s,metric=metric,capacity=0))
            self.assertTrue((out/'cleanup-empty.el').exists())

    def test_actual_v2_selection_rejects_unsupported_meta(self):
        script = 'set cv_test_only 1\nsource {'+str(m.NATIVE_TCL)+'}\n'+r'''
set selected {}
proc gui_list_get_selected {args} {
    global selected
    if {[lsearch -exact $args -meta] >= 0} {error unsupported-meta}
    switch -- [lindex $args end] {
        -flat {return $selected}
        -count {return [llength $selected]}
        -first {return [lindex $selected 0]}
        default {error unknown-option}
    }
}
proc gui_list_select {args} {
    global selected
    if {[lsearch -exact $args -select] >= 0} {set selected [list [lindex [lindex $args end] 0]]} else {set selected {}}
}
cv_select_detail exact-path exact-meta
puts SUPPORTED_SELECTION_PASS
'''
        wrapped = 'if {[catch {\n'+script+'\n} reason]} {puts stderr $reason; exit 1}\n'
        r = subprocess.run(['tclsh'], input=wrapped, text=True, capture_output=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('SUPPORTED_SELECTION_PASS', r.stdout)


if __name__ == '__main__':
    unittest.main()
