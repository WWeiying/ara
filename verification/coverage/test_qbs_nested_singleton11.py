"""Host model evidence only, never actual DVE qualification."""
import copy
from pathlib import Path
import tempfile
import tkinter
import unittest

import prepare_qbs_nested_singleton11 as p


class Singleton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record, cls.original = p.inputs()
        cls.candidate = cls.record['bounded_singleton_interface_study']['QBS_probe_candidate']

    def model(self, output, fault=None):
        t = tkinter.Tcl(); t.tk.wantobjects(False)
        t.eval('set qs_test_only 1'); t.eval(p.TCL.read_text())
        t.eval(p.selection(self.record, self.original, output))
        state = dict(cond='', vector='', active=False)
        expression = t.getvar('qs_expression'); parent = t.getvar('qs_parent')
        meta = parent+'  .'+expression
        def command(name, fn): t.createcommand(name, fn)
        def get(*args):
            option = args[2]; handle = args[3] if len(args) > 3 else None
            if option == '-firstChild': return '900' if handle is None else ('901' if handle == '900' else '')
            if option == '-nextSibling': return ''
            if option == '-path': return parent if handle == '900' else parent+'.'+expression
            if option == '-meta': return parent if handle == '900' else (meta+'bad' if fault == 'meta' else meta)
            raise AssertionError(args)
        def selected(*args):
            view = args[args.index('-list')+1]
            if '-all' in args:
                values = ('01', '10', '11') if state['cond'] == meta else ('00', '01', '10')
                if fault == 'truth': values = ('01', '11')
                return t.call('list', *values)
            value = state[view]
            return str(int(bool(value))) if '-count' in args else t.call('list', value)
        def select(*args):
            view = args[args.index('-list')+1]
            state[view] = '' if '-unselect' in args else t.splitlist(args[-1])[0]
        def exclusion(*args):
            if args == ('-reset',): state['active'] = False; return ''
            if '-recalculate' in args: return ''
            if '-excluded' in args:
                active = state['active'] and state['cond'] == meta and state['vector'] == '11'
                if fault == 'neighbor' and state['active'] and state['vector'] == '10': active = True
                return str(int(active))
            raise AssertionError(args)
        def exclude(*args):
            assert state['cond'] == meta and state['vector'] == '11'
            assert args[args.index('-list')+1] == 'vector'
            state['active'] = True
        def el(*args):
            path = Path(t.splitlist(args[-1])[0])
            if '-load' in args: state['active'] = True; return ''
            if not state['active']:
                path.write_bytes(b'bad' if fault == 'initial' else b''); return ''
            c = self.candidate
            text = 'CHECKSUM: "'+c['module_checksum']+' '+c['checksum']+'"\nINSTANCE: '+c['scope']+'\nANNOTATION: "'+p.f.proof.ANNOTATION+'"\n'
            line = 'Condition 700 "'+c['point']['attributes']['chksum']+'" "'+expression+' 1 -1" (77 "11")\n'
            if fault == 'extra': line += line
            if fault == 'checksum': text = text.replace(c['checksum'], '1')
            if fault == 'whole': line = 'Condition 700\n'
            if fault == 'reload' and path.name == 'second.el': line = line.replace('(77 ', '(78 ')
            path.write_text(text+line); return ''
        for name in ('gui_cov_show_cond_ids', 'gui_list_action', 'gui_list_expand'): command(name, lambda *a: '')
        command('gui_covdetail_query', lambda *a: 'Condition')
        command('gui_list_get', get); command('gui_list_get_selected', selected)
        command('gui_list_select', select); command('gui_exclusion', exclusion)
        command('gui_exclude_items', exclude); command('gui_exclusion_file', el)
        t.eval('set qbf_stream [open [file join $qs_output native-singleton.tcllist] w]')
        try:
            t.eval('qs_run')
            t.eval('gui_exclusion -reset; qs_save cleanup-empty.el 1; qbf_emit [list terminal 0 {} 0 {}]')
        finally: t.eval('close $qbf_stream')

    def test_actual_inputs_and_API_scope(self):
        p.safe()
        self.assertEqual(self.candidate['point']['raw_index'], 19670)
        self.assertEqual(self.candidate['point']['vector'], '11')

    def test_host_fullbody_singleton_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); self.model(out)
            result = p.inspect(out, self.candidate)
            self.assertEqual(result['protected_points'], 43005)
            self.assertFalse(result['full1792_qualified'])

    def test_host_negative_each_guard(self):
        for fault in ('initial', 'meta', 'truth', 'neighbor', 'extra', 'checksum', 'whole', 'reload'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(tkinter.TclError): self.model(Path(tmp), fault)

    def test_offline_native_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); self.model(out)
            original = (out/'first.el').read_text()
            changes = [(self.candidate['scope'], self.candidate['scope']+'bad'),
                ('4245564008', '1'), (' 1 -1', ' 2 -1'), ('(77 "11")', '(77 "01")'),
                ('Condition 700', 'Branch 700'), ('activation_valid_i[0]', 'activation_valid_i[1]')]
            for old, new in changes:
                with self.subTest(old=old):
                    self.assertEqual(original.count(old), 1)
                    (out/'first.el').write_text(original.replace(old, new))
                    with self.assertRaises(ValueError): p.inspect(out, self.candidate)
            for data in (original.encode()+original.encode(), b'', original.encode()+b'\xff\n'):
                (out/'first.el').write_bytes(data)
                with self.assertRaises(ValueError): p.inspect(out, self.candidate)

    def test_neighbor_lifecycle_missing_duplicate_and_terminal_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); self.model(out)
            path = out/'native-singleton.tcllist'; original = path.read_text()
            rows = original.splitlines(True)
            idx = next(i for i, row in enumerate(rows) if row.startswith('audit selected'))
            self.assertTrue(rows[idx].endswith(' 0\n'))
            for replacement in ('', rows[idx]+rows[idx], rows[idx][:-2]+'1\n'):
                changed = ''.join(rows[:idx])+replacement+''.join(rows[idx+1:])
                self.assertNotEqual(changed, original); path.write_text(changed)
                with self.assertRaises(ValueError): p.inspect(out, self.candidate)
            path.write_text(original.replace('terminal 0 {} 0 {}', 'terminal 1 failure 0 {}'))
            with self.assertRaises(ValueError): p.inspect(out, self.candidate)

    def test_empty_global_must_be_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); self.model(out)
            for name in ('initial-empty.el', 'before-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
                (out/name).write_bytes(b'INSTANCE: unexpected\n')
                with self.assertRaises(ValueError): p.inspect(out, self.candidate)
                (out/name).write_bytes(b'')

    def test_scope_drift_independent_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); self.model(out)
            c = copy.deepcopy(self.candidate); c['scope'] = c['scope'].replace('bank0', 'bank1')
            with self.assertRaises(ValueError): p.inspect(out, c)


if __name__ == '__main__': unittest.main()
