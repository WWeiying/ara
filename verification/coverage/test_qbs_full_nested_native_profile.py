"""Complete1344-group legacy-core session model, actual two-tree fixture and negatives."""
import copy
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import prepare_qbs_full_nested_native_profile as p


class FullProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads((p.f.PARENT/'proof-native-plan.json').read_bytes())

    def session(self, mutation=None):
        t = tkinter.Tcl(); t.tk.wantobjects(False)
        t.eval('''
            foreach command {lassign dict lmap try coroutine tailcall apply} {
                if {[llength [info commands $command]]} {rename $command {}}
            }
            set selected {}; set current {}; set mode 0; set transcript {}; set exited 0
            rename puts host_puts
            proc puts {args} {
                global transcript
                if {[llength $args] == 1} {lappend transcript [lindex $args 0]; return}
                host_puts [lindex $args 0] [lindex $args 1]
            }
            proc gui_open_cov {args} {}
            proc gui_list_expand {args} {}
            proc gui_exit {args} {global exited; set exited 1}
            proc gui_cov_show_cond_ids {args} {global mode; set mode [lindex $args end]}
            proc gui_list_action {args} {global current selected; set current [lindex $args end]; set selected {{}}}
            proc gui_covdetail_query {args} {return Condition}
            proc gui_list_get {args} {
                global current property mutation first_root
                set option [lindex $args 2]; set handle [lindex $args 3]
                if {$option eq "-firstChild" && $handle eq ""} {return $first_root($current)}
                if {$mutation eq "cycle" && $option eq "-nextSibling" && $handle eq $first_root($current)} {return $handle}
                if {$mutation eq "missingchild" && $option eq "-firstChild"} {return {}}
                if {$mutation eq "childpath" && $option eq "-path" && [string match hostChild* $handle]} {return wrong}
                if {![info exists property($current|$handle|$option)]} {error "Unknown actual handle/option"}
                return $property($current|$handle|$option)
            }
            proc gui_list_select {args} {
                global selected mutation
                if {[lsearch -exact $args -unselect] >= 0} {set selected {}; return}
                set meta [lindex [lindex $args end] 0]
                if {$mutation eq "selectreject" && [string first "  ." $meta] >= 0} {error "Child selector unsupported"}
                if {$mutation eq "readback"} {set meta wrong}
                set selected [list [list $meta]]
            }
            proc gui_list_get_selected {args} {
                global current selected mode vectors inventory mutation
                if {[lsearch -exact $args -columns] >= 0} {error "Hidden column forbidden"}
                if {[lsearch -exact $args -count] >= 0} {return [llength $selected]}
                if {[lsearch -exact $args vector] >= 0} {
                    if {$mutation eq "vectors"} {return {0 unknown}}
                    set meta [qbf_name $selected]
                    return $vectors($current|$meta)
                }
                if {[lsearch -exact $args -all] >= 0} {return $inventory($current)}
                if {$mode} {
                    if {$mutation eq "emptyIDs"} {return {}}
                    return [list opaque-observed-ID-display $selected]
                }
                return $selected
            }
        ''')
        t.setvar('mutation', mutation or '')
        rows = p.groups(self.artifact)
        actual_fixture = json.loads((p.CAPTURE/'capture-status.json').read_bytes())['observations']
        fixture_handles = {o['parent']: (o['actual_parent_handle'], o['matching_observed_handles'][0]) for o in actual_fixture}
        for bank, scope in enumerate(sorted(self.artifact['scope_protection'])):
            bank_rows = [g for g in rows if g['scope'] == scope]
            roots = [g for g in bank_rows if not g['parent']]
            handles = {}
            for i, g in enumerate(roots):
                handle = fixture_handles[g['expression']][0] if bank == 0 and g['expression'] in fixture_handles else 'hostRoot%d_%d' % (bank, i)
                handles[g['expression']] = handle
            allhandles = [handles[g['expression']] for g in roots]
            t.setvar('first_root('+scope+')', allhandles[0])
            t.setvar('inventory('+scope+')', tuple(g['expression'] for g in roots))
            for i, g in enumerate(roots):
                handle = handles[g['expression']]
                child = next((c for c in bank_rows if c['parent'] == g['expression']), None)
                ch = ''
                if child:
                    ch = fixture_handles[g['expression']][1] if bank == 0 and g['expression'] in fixture_handles else 'hostChild%d_%d' % (bank, i)
                    meta = g['expression']+'  .'+child['expression']
                    for option, value in (('-path', g['expression']+'.'+child['expression']), ('-meta', meta),
                                          ('-firstChild', ''), ('-nextSibling', '')):
                        t.setvar('property('+scope+'|'+ch+'|'+option+')', value)
                    t.setvar('vectors('+scope+'|'+meta+')', tuple(child['names']))
                for option, value in (('-path', g['expression']), ('-meta', g['expression']),
                                      ('-firstChild', ch), ('-nextSibling', allhandles[i+1] if i+1 < len(allhandles) else '')):
                    t.setvar('property('+scope+'|'+handle+'|'+option+')', value)
                t.setvar('vectors('+scope+'|'+g['expression']+')', tuple(g['names']))
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp); selection = output/'selection.tcl'
            selection.write_text(p.selection(self.artifact, Path('/sample.vdb'), 'sampletest'))
            t.setvar('env(QBS_SIDE1792_SELECTION)', str(selection)); t.setvar('env(QBS_SIDE1792_OUTPUT)', str(output))
            t.eval(p.TCL.read_text())
            raw = (output/'native-rows.tcllist').read_bytes()
        self.assertEqual(t.getvar('exited'), '1')
        return raw, t.getvar('transcript')

    def test_actual_parent80pins13artifacts_independent_recheck(self):
        actual = p.reviewed_capture()
        self.assertEqual(len(actual['observations']), 2)
        self.assertTrue(actual['not_full1792_qualification'])
        self.assertEqual(actual['observations'][0]['matching_observed_handles'], ['249094192'])

    def test_input_pin_drift_actual_ledger_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source'; path.write_text('frozen source')
            ledger = {str(path): p.f.sha(path)}
            p.f.check_pins(ledger)
            path.write_text('drift')
            with self.assertRaises(ValueError): p.f.check_pins(ledger)

    def test_entire1344_group_body_model_with_actual_two_tree_fixture(self):
        raw, transcript = self.session()
        self.assertIn('QBS_FULL_NESTED_DISCOVERY_COMPLETE_NATIVE_HOLD', transcript)
        result = p.inspect_rows(raw, self.artifact)
        self.assertEqual(result['nested_groups'], 448)
        self.assertEqual(result['actual_vectors'], 3584)
        self.assertFalse(result['numeric_signature_bound'])
        self.assertFalse(result['full_protection_qualified'])

    def test_entire_body_faults_preserve_partial_and_hold(self):
        for mutation in ('cycle', 'missingchild', 'childpath', 'readback', 'vectors', 'selectreject'):
            raw, transcript = self.session(mutation)
            with self.subTest(mutation=mutation):
                self.assertIn('QBS_FULL_NESTED_HOLD', transcript)
                with self.assertRaises(ValueError): p.inspect_rows(raw, self.artifact)
        raw, _ = self.session('selectreject')
        self.assertIn(b'object ', raw)  # Child identity survives an unsupported selection API.

    def test_emptyIDs_not_false_success(self):
        raw, _ = self.session('emptyIDs')
        with self.assertRaises(ValueError): p.inspect_rows(raw, self.artifact)

    def test_captured_row_missing_duplicate_scope_handle_meta_vector_ID_terminal(self):
        raw, _ = self.session()
        lines = raw.splitlines(keepends=True)
        group = next(l for l in lines if l.startswith(b'group '))
        obj = next(l for l in lines if l.startswith(b'object '))
        mutations = [raw.replace(group, b'', 1), raw.replace(group, group+group, 1),
            raw.replace(obj, obj+obj, 1), raw.replace(b'i_payload_buffer', b'i_foreign_buffer', 1),
            b''.join(lines[:-1]), raw+b'extra\n', raw.replace(b'FULL1792_NATIVE_HOLD', b'QUALIFIED')]
        t = tkinter.Tcl()
        for index, value in ((4, 'wrongHandle'), (6, 'wrongMeta'), (8, '0 unknown'), (9, '')):
            fields = list(t.splitlist(group.decode().strip())); fields[index] = value
            t.setvar('fixture', tuple(fields)); replaced = (t.eval('list {*}$fixture')+'\n').encode()
            mutations.append(raw.replace(group, replaced, 1))
        for changed in mutations:
            self.assertNotEqual(changed, raw)
            with self.assertRaises(ValueError): p.inspect_rows(changed, self.artifact)

    def test_nonascii_IDdisplay_bytes_are_not_sanitized(self):
        raw, _ = self.session()
        changed = raw.replace(b'opaque-observed-ID', b'\xc8opaque-observed-ID', 1)
        with self.assertRaises(UnicodeDecodeError): p.inspect_rows(changed, self.artifact)

    def test_scope_proof_population_drift_rejected(self):
        for field in ('native_groups',):
            changed = copy.deepcopy(self.artifact); changed[field].pop()
            with self.assertRaises(ValueError): p.groups(changed)
        changed = copy.deepcopy(self.artifact); changed['native_groups'][0]['scope'] = 'foreign'
        with self.assertRaises(ValueError): p.selection(changed, Path('/sample.vdb'), 'sampletest')

    def test_full_input_actual_eval_and_compiledIDs_never_selected(self):
        changed = copy.deepcopy(self.artifact)
        for g in changed['native_groups']: g['compiled_identity_NOT_GUI'] = ['DO_NOT_USE_THIS_ID', 'bogus']
        text = p.selection(changed, Path('/sample.vdb'), 'sampletest')
        self.assertNotIn('DO_NOT_USE_THIS_ID', text)
        for previous_handle in ('249093280', '249094192', '249147360', '249148272'):
            self.assertNotIn(previous_handle, text)
        self.assertEqual(text.count('lappend qbf_groups '), 1344)

    def test_strict_readonly_legacy_allowlist(self):
        p.safe_tcl(p.TCL.read_text())
        for tail in ('gui_exclusion -reset', 'gui_import x', 'gui_list_get -text 4', 'exec x',
                     'eval x', 'lassign x', 'dict x', 'source other'):
            with self.subTest(tail=tail), self.assertRaises(ValueError): p.safe_tcl(p.TCL.read_text()+'\n'+tail)

    def test_unauthorized_capture_no_spawn(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(p.f.subprocess, 'Popen') as spawn:
            receipt = Path(tmp)/'receipt'; receipt.write_text(json.dumps(dict(source='USER_REPORTED')))
            with self.assertRaises(ValueError): p.f.capture(Path(tmp), 'a'*64, receipt)
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
