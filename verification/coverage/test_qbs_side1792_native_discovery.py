"""Host session model and strict discovery-reader negatives; no EDA/qualification."""
import copy
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import prepare_qbs_side1792_native_discovery as d


class Discovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads((d.PARENT/'proof-native-plan.json').read_bytes())

    def capture(self):
        interp = tkinter.Tcl()
        def row(*values):
            # Tcl itself formats the nested lists, including expression wrappers.
            interp.setvar('fixture_values', values)
            return interp.eval('list {*}$fixture_values')
        lines = [row('input', str(d.proof.DESIGN), 'sample', 'sampletest')]
        for scope in sorted(self.artifact['scope_protection']):
            groups = [g for g in self.artifact['native_groups'] if g['scope'] == scope]
            names = interp.eval('list ' + ' '.join(d.tcl_word(g['expression']) for g in groups))
            lines.append(row('inventory', scope, names))
            for g in groups:
                vectors = interp.eval('list ' + ' '.join(d.tcl_word(n) for n in g['names']))
                selected = interp.eval('list ' + d.tcl_word(g['expression']))
                lines.append(row('group', scope, g['expression'], selected, vectors))
            lines.append(row('ids_display', scope, 'observed-display-not-a-signature'))
            lines.append(row('scope_complete', scope, '672'))
        lines.append(row('complete', '1344', 'NATIVE_SIGNATURE_HOLD'))
        return ('\n'.join(lines)+'\n').encode('ascii')

    def test_full_host_capture_not_native_qualification(self):
        result = d.inspect_rows(self.capture(), self.artifact)
        self.assertEqual(result['groups'], 1344)
        self.assertFalse(result['native_qualified'])

    def test_nonascii_preserved_and_rejected(self):
        raw = self.capture().replace(b'observed-display', b'\xc8observed-display', 1)
        with self.assertRaises(UnicodeDecodeError):
            d.inspect_rows(raw, self.artifact)
        self.assertIn(b'\xc8', raw)

    def test_capture_negatives(self):
        good = self.capture()
        lines = good.splitlines(keepends=True)
        group = next(l for l in lines if l.startswith(b'group '))
        mutations = {
            'missing': good.replace(group, b'', 1),
            'duplicate': good.replace(group, group+group, 1),
            'foreign_scope': good.replace(b'i_payload_buffer', b'i_foreign_buffer', 1),
            'extra_record': good+b'group foreign\n',
            'no_terminal': b''.join(lines[:-1]),
            'false_qualified': good.replace(b'NATIVE_SIGNATURE_HOLD', b'QUALIFIED'),
            'nul': good+b'\x00\n',
            'wrong_count': good.replace(b'scope_complete ', b'bad_complete ', 1),
        }
        for name, raw in mutations.items():
            self.assertNotEqual(raw, good, name)
            with self.subTest(name=name), self.assertRaises((ValueError, tkinter.TclError)):
                d.inspect_rows(raw, self.artifact)

    def test_vector_and_selected_readback_mutations(self):
        raw = self.capture()
        interp = tkinter.Tcl()
        line = next(l for l in raw.decode().splitlines() if l.startswith('group '))
        fields = list(interp.splitlist(line))
        for index, value in ((3, 'wrong selection'), (4, '0 1 unknown')):
            mutated = list(fields); mutated[index] = value
            interp.setvar('fixture_values', tuple(mutated))
            replacement = interp.eval('list {*}$fixture_values')
            with self.subTest(index=index), self.assertRaises(ValueError):
                d.inspect_rows(raw.replace(line.encode(), replacement.encode(), 1), self.artifact)

    def test_static_readonly_allowlist(self):
        text = d.TCL.read_text()
        d.safe_tcl(text)
        for addition in ('gui_exclusion -reset', 'gui_import foo', 'exec foo', 'eval foo',
                         'gui_list_get_selected -columns {ID}', 'after 1 foo', 'source other'):
            with self.subTest(addition=addition), self.assertRaises(ValueError):
                d.safe_tcl(text+'\n'+addition)

    def test_selection_never_uses_compiled_ids(self):
        changed = copy.deepcopy(self.artifact)
        for g in changed['native_groups']:
            g['compiled_identity_NOT_GUI'] = ['DO_NOT_SELECT_ME', 'bogus']
        result = d.selection(changed, Path('/sample.vdb'), 'sampletest')
        self.assertNotIn('DO_NOT_SELECT_ME', result)
        self.assertNotIn('bogus', result)

    def test_group_population_rejections(self):
        for mode in ('missing', 'whole', 'duplicate', 'foreign'):
            artifact = copy.deepcopy(self.artifact)
            if mode == 'missing': artifact['native_groups'].pop()
            if mode == 'whole': artifact['native_groups'][0]['retained'] = []
            if mode == 'duplicate': artifact['native_groups'][1] = artifact['native_groups'][0]
            if mode == 'foreign': artifact['native_groups'][0]['scope'] = 'foreign'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                d.selection(artifact, Path('/sample.vdb'), 'sampletest')

    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'pin'; p.write_text('original')
            pins = {str(p): d.sha(p)}
            d.check_pins(pins)
            p.write_text('changed')
            with self.assertRaises(ValueError): d.check_pins(pins)

    def session(self, selected='{}', wrong=False, vectors='0 1'):
        t = tkinter.Tcl()
        t.eval('set qsd_test_only 1')
        t.eval(d.TCL.read_text())
        t.eval('''
            set selected {}; set actions {}; set emitted {}
            proc qsd_emit {row} {global emitted; lappend emitted $row}
            proc gui_cov_show_cond_ids {args} {}
            proc gui_list_action {args} {}
            proc gui_covdetail_query {args} {return Condition}
            proc gui_list_select {args} {
                global selected actions wrong
                lappend actions $args
                set name [lindex [lindex $args end] 0]
                if {[lsearch -exact $args -unselect] >= 0} {set selected {}; return}
                if {$wrong} {set selected {{wrong}}} else {set selected [list [list $name]]}
            }
            proc gui_list_get_selected {args} {
                global selected vectors
                if {[lsearch -exact $args -count] >= 0} {return [llength $selected]}
                if {[lsearch -exact $args vector] >= 0} {return $vectors}
                if {[lsearch -exact $args -all] >= 0} {return [list {(a ? b : c)}]}
                return $selected
            }
        ''')
        t.setvar('selected', selected)
        t.setvar('wrong', int(wrong))
        t.setvar('vectors', vectors)
        return t

    def test_empty_selected_actual_shape(self):
        for raw in ('', '{}', '{{}}'):
            t = self.session(selected=raw)
            t.eval('qsd_clear')
            self.assertEqual(t.eval('llength $actions'), '0')

    def test_do_not_trim_nonempty(self):
        t = self.session(selected='{ }')
        t.eval('qsd_clear')
        self.assertEqual(t.eval('llength $actions'), '1')
        self.assertEqual(t.eval('lindex [lindex $actions 0] end'), '{ }')

    def test_actual_session_wrappers(self):
        t = self.session()
        t.eval('qsd_scope scope [list [list {(a ? b : c)} {0 1}]]')
        self.assertIn('scope_complete', t.eval('set emitted'))

    def test_wrong_readback_and_vector(self):
        for t in (self.session(wrong=True), self.session(vectors='0 unknown')):
            with self.assertRaises(tkinter.TclError):
                t.eval('qsd_scope scope [list [list {(a ? b : c)} {0 1}]]')

    def test_no_launch_during_prepare(self):
        with patch.object(d, 'prepare') as prepared, patch.object(d.sys, 'argv',
            ['tool', 'prepare', '--output', str(d.proof.OUT/'unused')]):
            d.main()
            prepared.assert_called_once()

    def test_scope_boundary_is_not_four_state_claim(self):
        self.assertFalse(d.SCOPE_BOUNDARY['boolean_checks_are_four_state_proof'])
        self.assertTrue(d.SCOPE_BOUNDARY['excludes_X_and_delta'])
        self.assertIn('not known1', d.SCOPE_BOUNDARY['limitation'])

    def test_authorization_exact_parent_not_user_reported(self):
        receipt = dict(source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL', plan_seal='a'*64,
            action='ONE_READ_ONLY_NATIVE_DISCOVERY', budget_seconds=300, exclusions=False, application=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            path.write_text(json.dumps(receipt))
            d.authorization(path, 'a'*64)
            for key, value in (('source', 'USER_REPORTED'), ('plan_seal', 'b'*64),
                               ('budget_seconds', 600), ('exclusions', True), ('application', True)):
                changed = dict(receipt); changed[key] = value
                path.write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    d.authorization(path, 'a'*64)

    def test_unauthorized_capture_cannot_spawn(self):
        with patch.object(d.subprocess, 'Popen') as spawn, self.assertRaises(ValueError), \
             patch.object(d.sys, 'argv', ['tool', 'capture-readonly', '--output', str(d.proof.OUT/'unused')]):
            d.main()
        spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
