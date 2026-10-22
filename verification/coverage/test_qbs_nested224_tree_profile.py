"""Complete legacy-core profile session and capture negatives; no EDA launch."""
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import prepare_qbs_nested224_tree_profile as p


class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads((p.f.PARENT/'proof-native-plan.json').read_bytes())

    def session(self, mutation=None):
        interp = tkinter.Tcl(); interp.tk.wantobjects(False)
        interp.eval('''
            rename lassign {}; rename dict {}
            set transcript {}; set exited 0
            rename puts host_puts
            proc puts {args} {
                global transcript
                if {[llength $args] == 1} {lappend transcript [lindex $args 0]; return}
                host_puts [lindex $args 0] [lindex $args 1]
            }
            proc gui_open_cov {args} {global opened; set opened $args}
            proc gui_list_expand {args} {}
            proc gui_cov_show_cond_ids {args} {}
            proc gui_list_action {args} {global action; set action $args}
            proc gui_covdetail_query {args} {return Condition}
            proc gui_exit {args} {global exited; set exited 1}
            proc gui_list_get {args} {
                global rootmeta childmeta paths mutation
                set option [lindex $args 2]; set handle [lindex $args 3]
                if {$option eq "-firstChild"} {
                    if {$handle eq ""} {return actualA}
                    if {$mutation eq "missingchild"} {return {}}
                    if {$handle eq "actualA"} {return actualChildA}
                    if {$handle eq "actualB"} {return actualChildB}
                    return {}
                }
                if {$option eq "-nextSibling"} {
                    if {$handle eq "actualA"} {
                        if {$mutation eq "cycle"} {return actualA}
                        return actualB
                    }
                    return {}
                }
                if {$option eq "-childCount"} {
                    if {$handle eq "actualA" || $handle eq "actualB"} {return 1}
                    return 0
                }
                if {$option eq "-path"} {return $paths($handle)}
                if {$option eq "-meta"} {
                    if {$handle eq "actualA" || $handle eq "actualB"} {return $rootmeta($handle)}
                    return $childmeta($handle)
                }
                error "Unexpected API option"
            }
        ''')
        examples = p.profile()['examples']
        for suffix, ex in zip(('A', 'B'), examples):
            parent, child = ex['parent_expression'], ex['child_expression']
            interp.setvar('rootmeta(actual'+suffix+')', parent)
            interp.setvar('paths(actual'+suffix+')', parent)
            interp.setvar('paths(actualChild'+suffix+')', parent+'.'+child)
            interp.setvar('childmeta(actualChild'+suffix+')', parent+'  .'+child)
        interp.setvar('mutation', mutation or '')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            selection = output/'selection.tcl'
            selection.write_text(p.selection(self.artifact, Path('/sample.vdb'), 'sampletest'))
            interp.setvar('env(QBS_SIDE1792_SELECTION)', str(selection))
            interp.setvar('env(QBS_SIDE1792_OUTPUT)', str(output))
            interp.eval(p.TCL.read_text())
            raw = (output/'native-rows.tcllist').read_bytes()
        self.assertEqual(interp.getvar('exited'), '1')
        return raw, interp.getvar('transcript')

    def test_entire_two_parent_session_old_core_model(self):
        raw, transcript = self.session()
        self.assertIn('QBS_NESTED_TWO_PARENT_COMPLETE_NATIVE_HOLD', transcript)
        result = p.inspect_rows(raw, self.artifact)
        self.assertEqual(result['captured_nodes'], 4)
        self.assertFalse(result['native_qualified'])
        self.assertEqual(result['target_count'], 1792)
        self.assertEqual(result['protected_condition_count'], 41214)
        self.assertEqual([x['matching_observed_handles'] for x in result['observations']],
                         [['actualChildA'], ['actualChildB']])

    def test_cycle_and_nochild_actualbody_hold(self):
        for mutation in ('cycle', 'missingchild'):
            raw, transcript = self.session(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                p.inspect_rows(raw, self.artifact)
            self.assertIn('QBS_NESTED_TWO_PARENT_HOLD', transcript)

    def test_capture_missing_duplicate_handle_count_depth_terminal(self):
        raw, _ = self.session()
        lines = raw.splitlines(keepends=True)
        child = next(x for x in lines if x.startswith(b'child 1 '))
        mutations = (raw.replace(child, b'', 1), raw.replace(child, child+child, 1),
            raw.replace(b'child 1 ', b'child 9 ', 1), raw+b'extra\n',
            b''.join(lines[:-1]), raw.replace(b'NATIVE_IDENTITY_HOLD', b'QUALIFIED'))
        for changed in mutations:
            self.assertNotEqual(changed, raw)
            with self.assertRaises(ValueError): p.inspect_rows(changed, self.artifact)

    def test_raw_nonascii_never_sanitized(self):
        raw, _ = self.session()
        changed = raw.replace(b'actualChildA', b'\xc8actualChildA', 1)
        with self.assertRaises(UnicodeDecodeError): p.inspect_rows(changed, self.artifact)

    def test_different_observed_child_shape_is_identity_hold(self):
        raw, _ = self.session()
        interp = tkinter.Tcl()
        line = next(x for x in raw.decode().splitlines() if x.startswith('child 1 '))
        fields = list(interp.splitlist(line)); fields[4] = 'observed other native shape'
        interp.setvar('fields', tuple(fields)); replacement = interp.eval('list {*}$fields')
        result = p.inspect_rows(raw.replace(line.encode(), replacement.encode(), 1), self.artifact)
        self.assertEqual(result['observations'][0]['relation'], 'HOLD_OTHER_OR_AMBIGUOUS_SHAPE')
        self.assertFalse(result['native_qualified'])

    def test_strict_readonly_body_and_entry(self):
        p.safe_tcl(p.TCL.read_text())
        for tail in ('gui_exclusion -reset', 'gui_list_select x', 'exec x', 'eval x',
                     'gui_list_get -text 4', 'source other'):
            with self.subTest(tail=tail), self.assertRaises(ValueError): p.safe_tcl(p.TCL.read_text()+'\n'+tail)

    def test_wrong_authorization_no_spawn(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p.f.subprocess, 'Popen') as spawn:
            receipt = Path(tmp)/'receipt.json'; receipt.write_text(json.dumps(dict(source='USER_REPORTED')))
            with self.assertRaises(ValueError): p.f.capture(Path(tmp), 'a'*64, receipt)
            spawn.assert_not_called()

    def test_actual_success_API_evidence_is_pinned_not_QBS_claim(self):
        study = json.loads(p.STUDY.read_bytes())
        self.assertEqual(study['historical_tree_rows'], 36)
        self.assertTrue(study['help_not_equivalent_to_QBS_child_capture'])
        p.f.check_pins(study['pins'])

    def test_generated_profile_is_two_only_no_XMLids(self):
        text = p.selection(self.artifact, Path('/sample.vdb'), 'sampletest')
        interp = tkinter.Tcl(); interp.tk.wantobjects(False); interp.eval(text)
        self.assertEqual(len(interp.splitlist(interp.getvar('qnt_parents'))), 2)
        self.assertNotIn('compiled_identity', text)
        self.assertNotIn('qsd_scopes', text)


if __name__ == '__main__':
    unittest.main()
