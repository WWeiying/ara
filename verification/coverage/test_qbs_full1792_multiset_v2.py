"""Actual failed-order fixture plus full host body; never salvages missing final stage."""
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import prepare_qbs_full1792_multiset_v2 as p
import test_qbs_full1792_qualification as fixture


REAL_TCL = tkinter.Tcl


class FullSuccessor(fixture.Full):
    @classmethod
    def setUpClass(cls):
        p.configure()
        super().setUpClass()

    def model(self, output, fault=None, reordered=False):
        def factory(*args,**kwargs):
            t=REAL_TCL(*args,**kwargs); t.tk.wantobjects(False); t.setvar('qnm_test_only','1')
            create=t.createcommand
            def register(name,callback):
                if name=='gui_exclusion_file' and reordered:
                    def wrapped(*argv):
                        result=callback(*argv)
                        path=Path(t.splitlist(argv[-1])[0])
                        if '-save' in argv and path.name=='second.el':
                            lines=path.read_text().splitlines(True)
                            self.assertEqual(len(lines),4*1792)
                            blocks=[lines[i:i+4] for i in range(0,len(lines),4)]
                            path.write_text(''.join(line for block in reversed(blocks) for line in block))
                        return result
                    return create(name,wrapped)
                return create(name,callback)
            t.createcommand=register
            return t
        with patch('tkinter.Tcl',factory): super().model(output,fault)

    def test_entire_body_reordered_EL_still_requires_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); self.model(out,reordered=True)
            self.assertNotEqual((out/'first.el').read_bytes(),(out/'second.el').read_bytes())
            result=p.inspect(out,self.artifact)
            self.assertEqual(result['protected_count'],41214)
            self.assertTrue(result['five_stages_pass']); self.assertFalse(result['application'])
            (out/'final-empty.el').unlink()
            with self.assertRaises(OSError): p.inspect(out,self.artifact)

    def test_actual_order_fixture_and_original_HOLD(self):
        actual=p.failure_evidence(self.artifact)
        self.assertTrue(actual['exact_identity_attribute_annotation_multiset_equal'])
        self.assertFalse(actual['qualification_salvaged'])
        self.assertFalse(actual['raw_bytes_equal'])
        with self.assertRaises((ValueError,OSError)): p.inspect(p.FAILED,self.artifact)

    def test_actual_annotated_identity_attribute_mutations(self):
        first=(p.FAILED/'first.el').read_bytes(); second=(p.FAILED/'second.el').read_bytes()
        p.equivalent(first,second,self.artifact)
        changes=[(b'Condition 8260 ',b'Condition 999999 '), (b'(3 "11")',b'(999 "11")'),
            (b'4245564008',b'4245564009'), (b'1651389237',b'1651389238'),
            (b'2947893042',b'2947893043'), (b' 1 -1',b' 2 -1'), (b' 1 -1',b' 1 0'),
            (b'bank0',b'bank2'), (b'activation_valid_i[0]',b'activation_valid_i[1]'),
            (b'(3 "11")',b'(3 "10")'),(b'vcs_gen_start:row=0,b=0:',b'vcs_gen_start:row=1,b=0:')]
        for old,new in changes:
            with self.subTest(field=old):
                self.assertIn(old,second); changed=second.replace(old,new,1); self.assertNotEqual(changed,second)
                with self.assertRaises(ValueError): p.equivalent(first,changed,self.artifact)
        lines=second.splitlines(True)
        annotation=next(i for i,line in enumerate(lines) if line.startswith(b'ANNOTATION:'))
        for changed in (second+second,b''.join(lines[:annotation]+lines[annotation+1:]),
                        second.replace(b'Condition 8289',b'Branch 8289',1),second+b'\xff\n',
                        second.replace(b'\n',b'\n\n',1),second[:-1]):
            self.assertNotEqual(changed,second)
            with self.assertRaises(ValueError): p.equivalent(first,changed,self.artifact)

    def test_actual_nem_primitive_Tcl_and_annotation_swap(self):
        t=REAL_TCL(); t.tk.wantobjects(False)
        t.eval('''foreach command {lassign dict lmap try coroutine tailcall apply} {
            if {[llength [info commands $command]]} {rename $command {}}
        }''')
        t.eval(p.MULTISET.read_text())
        first=(p.FAILED/'first.el').read_text(); second=(p.FAILED/'second.el').read_text()
        self.assertEqual(t.call('nem_require_equal',first,second),'1792')
        # Both annotations remain permitted by bind_native, but their owner association changes.
        annotations=[line for line in second.splitlines() if line.startswith('ANNOTATION:')]
        a=annotations[0]; b=next(x for x in annotations if x!=a)
        changed=second.replace(a,'TEMPORARY_SENTINEL',1).replace(b,a,1).replace('TEMPORARY_SENTINEL',b,1)
        self.assertNotEqual(changed,second)
        p.f.proof.bind_native(changed.encode('ascii'),self.artifact['candidates'])
        with self.assertRaises(ValueError): p.equivalent(first.encode('ascii'),changed.encode('ascii'),self.artifact)
        with self.assertRaises(tkinter.TclError): t.call('nem_require_equal',first,changed)


if __name__=='__main__': unittest.main()
