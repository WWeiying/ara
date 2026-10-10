"""Run complete capture body in a restricted-core host session, never EDA."""
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import prepare_qbs_side1792_native_discovery_v3 as v3
import test_qbs_side1792_native_discovery_v2 as v2tests


class Legacy(v2tests.Successor):
    def full_session(self, script=None, actual_inventory=False, mutation=None):
        script = v3.TCL if script is None else script
        t = tkinter.Tcl(); t.tk.wantobjects(False)
        t.eval('''
            foreach command {lassign dict lmap try coroutine tailcall apply} {
                if {[llength [info commands $command]]} {rename $command {}}
            }
            rename lsort host_lsort
            proc lsort {args} {
                if {[llength $args] == 1} {return [host_lsort [lindex $args 0]]}
                if {[llength $args] == 2 && [lindex $args 0] eq "-unique"} {
                    return [host_lsort -unique [lindex $args 1]]
                }
                error "Unsupported legacy lsort option"
            }
            rename puts host_puts
            set transcript {}; set selected {{{}}}; set scope {}; set exited 0
            proc puts {args} {
                global transcript
                if {[llength $args] == 1} {lappend transcript [lindex $args 0]; return}
                host_puts [lindex $args 0] [lindex $args 1]
            }
            proc gui_cov_show_cond_ids {args} {}
            proc gui_open_cov {args} {global opened; set opened 1}
            proc gui_list_expand {args} {}
            proc gui_exit {args} {global exited; set exited 1}
            proc gui_list_action {args} {global scope; set scope [lindex $args end]}
            proc gui_covdetail_query {args} {return Condition}
            proc gui_list_select {args} {
                global selected mutation
                if {[lsearch -exact $args -unselect] >= 0} {set selected {}; return}
                set name [lindex [lindex $args end] 0]
                if {$mutation eq "readback"} {set name wrong}
                set selected [list [list $name]]
            }
            proc gui_list_get_selected {args} {
                global selected scope inventories vectors mutation
                if {[lsearch -exact $args -columns] >= 0} {error "Hidden columns forbidden"}
                if {[lsearch -exact $args vector] >= 0} {
                    if {$mutation eq "vector"} {return {0 unknown}}
                    set expression [qsd_name $selected]
                    return $vectors($scope|$expression)
                }
                if {[lsearch -exact $args -all] >= 0} {return $inventories($scope)}
                if {[lsearch -exact $args -count] >= 0} {return [llength $selected]}
                return $selected
            }
        ''')
        t.setvar('mutation', mutation or '')
        for scope in sorted(self.artifact['scope_protection']):
            groups = [g for g in self.artifact['native_groups'] if g['scope'] == scope]
            t.setvar('inventories('+scope+')', tuple(g['expression'] for g in groups))
            for g in groups:
                t.setvar('vectors('+scope+'|'+g['expression']+')', tuple(g['names']))
        if actual_inventory:
            rows = [t.splitlist(l) for l in (v3.FAILED/'native-rows.tcllist').read_text().splitlines()]
            row = next(r for r in rows if r[0] == 'inventory')
            t.setvar('inventories('+row[1]+')', row[2])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            selection = output/'selection.tcl'
            selection.write_text(v3.v2.selection(self.artifact, Path('/sample.vdb'), 'sampletest'))
            t.setvar('env(QBS_SIDE1792_SELECTION)', str(selection))
            t.setvar('env(QBS_SIDE1792_OUTPUT)', str(output))
            # Execute entry, source, open/write/close, two scopes and all1344 selections.
            t.eval(script.read_text())
            raw = (output/'native-rows.tcllist').read_bytes()
        self.assertEqual(t.getvar('exited'), '1')
        return raw, t.getvar('transcript')

    def test_full_legacy_body_all1344_not_native_evidence(self):
        raw, transcript = self.full_session()
        self.assertIn('QBS_SIDE1792_DISCOVERY_COMPLETE_SIGNATURE_HOLD', transcript)
        with patch.object(v3.frozen, 'TCL', v3.TCL):
            result = v3.frozen.inspect_rows(raw, self.artifact)
        self.assertEqual(result['groups'], 1344)
        self.assertFalse(result['native_qualified'])

    def test_old_body_reproduces_actual_lassign_error(self):
        raw, transcript = self.full_session(script=v3.OLD_TCL)
        self.assertIn('invalid command name', transcript)
        self.assertIn('lassign', transcript)
        self.assertNotIn('scope_complete', raw.decode())

    def test_actual_inventory_nested224_is_hold_not_dropped(self):
        raw, transcript = self.full_session(actual_inventory=True)
        self.assertIn('Expected expression absent', transcript)
        self.assertNotIn('scope_complete', raw.decode())
        evidence = v3.compatibility_evidence()
        self.assertEqual(evidence['actual_inventory']['missing_groups'], 224)
        self.assertEqual(evidence['actual_inventory']['present_groups'], 448)

    def test_full_body_readback_and_vector_mutations(self):
        for mutation, message in (('readback', 'Exact expression selection failed'),
                                  ('vector', 'Truth table differs')):
            raw, transcript = self.full_session(mutation=mutation)
            with self.subTest(mutation=mutation):
                self.assertIn(message, transcript)
                self.assertNotIn('scope_complete', raw.decode())

    def test_complete_command_audit(self):
        evidence = v3.audit_tcl()
        self.assertIn('lsort -unique', evidence['commands'])
        self.assertFalse(evidence['hidden_columns'])
        self.assertFalse(evidence['command_expansion'])
        self.assertTrue(evidence['unsupported_lassign_replaced'])

    def test_v3_api_diff_only_pair_shape_and_version_logging(self):
        old, new = v3.OLD_TCL.read_text(), v3.TCL.read_text()
        import re
        self.assertEqual(re.findall(r'\bgui_\w+[^\n]*', old), re.findall(r'\bgui_\w+[^\n]*', new))


if __name__ == '__main__':
    unittest.main()
