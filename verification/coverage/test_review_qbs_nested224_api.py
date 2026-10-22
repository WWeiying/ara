import copy
import json
from pathlib import Path
import tempfile
import tkinter
import unittest

import review_qbs_nested224_api as r


class Study(unittest.TestCase):
    def test_actual_all224_unique_parents_and_historical_API(self):
        evidence = r.evidence()
        self.assertEqual(len(evidence['actual_parent_mappings']), 224)
        self.assertEqual(evidence['historical_tree_rows'], 36)
        self.assertFalse(evidence['native_qualified'])
        self.assertEqual(evidence['proposed_probe']['parent_count'], 2)

    def test_missing_or_ambiguous_parent_rejected(self):
        artifact = json.loads((r.f.PARENT/'proof-native-plan.json').read_bytes())
        evidence = r.evidence()
        scope = evidence['proposed_probe']['scope']
        names = {g['expression'] for g in artifact['native_groups'] if g['scope'] == scope and
                 not g['expression'].startswith(('(weight_valid_i[0]', '(activation_valid_i[0]'))}
        r.pairs(artifact, scope, names)
        parent = evidence['actual_parent_mappings'][0]['parent_expression']
        with self.assertRaises(ValueError): r.pairs(artifact, scope, names-{parent})
        duplicate = copy.deepcopy(artifact)
        duplicate['native_groups'].append(next(g for g in duplicate['native_groups'] if g['scope'] == scope and g['expression'] == parent))
        with self.assertRaises(ValueError): r.pairs(duplicate, scope, names)

    def run_probe(self, mutation=None):
        t = tkinter.Tcl(); t.tk.wantobjects(False)
        t.eval('''
            rename lassign {}; rename dict {}
            set qnt_scope bank0; set qnt_parents {parentA parentB}
            proc gui_list_action {args} {}
            proc gui_cov_show_cond_ids {args} {}
            proc gui_covdetail_query {args} {return Condition}
            proc gui_list_expand {args} {}
            proc gui_list_get {args} {
                global mutation
                set option [lindex $args 2]; set handle [lindex $args 3]
                if {$option eq "-firstChild"} {
                    if {$handle eq ""} {return hA}
                    if {$mutation eq "missingchild"} {return {}}
                    if {$handle eq "hA"} {return cA}
                    if {$handle eq "hB"} {return cB}
                    return {}
                }
                if {$option eq "-nextSibling"} {
                    if {$mutation eq "cycle" && $handle eq "hA"} {return hA}
                    if {$handle eq "hA"} {return hB}
                    return {}
                }
                if {$option eq "-childCount"} {return 1}
                if {$handle eq "hA"} {return parentA}
                if {$handle eq "hB"} {return parentB}
                if {$handle eq "cA"} {return {parentA  .childA}}
                return {parentB  .childB}
            }
        ''')
        t.setvar('mutation', mutation or '')
        t.setvar('qnt_scope', 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0.i_payload_buffer')
        t.eval(r.TCL.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'rows'
            t.setvar('output', str(file)); t.eval('set qnt_stream [open $output w]')
            try:
                t.eval('qnt_probe')
            finally:
                t.eval('close $qnt_stream')
            return file.read_text()

    def test_full_probe_actual_handle_model(self):
        text = self.run_probe()
        self.assertIn('NATIVE_IDENTITY_HOLD', text)
        self.assertIn('parentA  .childA', text)

    def test_cycle_and_missing_child_hold(self):
        for mutation in ('cycle', 'missingchild'):
            with self.subTest(mutation=mutation), self.assertRaises(tkinter.TclError):
                self.run_probe(mutation)

    def test_no_columns_select_exclusion_or_compiledIDs(self):
        text = r.TCL.read_text()
        for word in ('-columns', '-text', 'gui_list_select', 'gui_exclusion', 'gui_import', 'lassign ', 'dict ', 'compiled_identity'):
            self.assertNotIn(word, text)


if __name__ == '__main__':
    unittest.main()
