import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest import mock
import soc_constants61_native_v2 as v


class AliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((v.RUN/'config.json').read_text())
        cls.instance=cls.config['instances'][15]
        cls.text=(v.RUN/'native_before_15.tsv').read_text()
        cls.label='orig_instr.rvftype.repl'

    def test_actual_all18_complete(self):
        q=v.replay()
        self.assertEqual((q['scopes'],q['rows'],len(q['aliases'])),(18,9012,1))
        self.assertEqual(q['aliases'][0]['compiled']['left'],'14')
        self.assertTrue(q['aliases'][0]['protected'])

    def test_original_rejection_and_exact_new_binding(self):
        with self.assertRaises(Exception):v.old.bind(self.instance,self.text)
        self.assertEqual(len(v.bind(self.instance,self.text)),len(v.old.primitive.old.frozen.pack.native.native_rows(self.text)))

    def test_multibit_bare_rejected(self):
        i=copy.deepcopy(self.instance)
        next(n for n in i['typed_objects'] if n['name']==self.label)['right']='13'
        with self.assertRaises(Exception):v.bind(i,self.text)

    def test_port_role_rejected(self):
        with self.assertRaises(Exception):
            v.bind(self.instance,self.text.replace(self.label+'\tsignal\t',self.label+'\tport\t'))

    def test_unknown_union_member_rejected(self):
        with self.assertRaises(Exception):v.bind(self.instance,self.text.replace(self.label,self.label+'unknown'))

    def test_missing_protected_member_rejected(self):
        text='\n'.join(line for line in self.text.splitlines() if self.label not in line)+'\n'
        with self.assertRaises(Exception):v.bind(self.instance,text)

    def test_duplicate_compiled_owner_rejected(self):
        i=copy.deepcopy(self.instance)
        i['typed_objects'].append(copy.deepcopy(next(n for n in i['typed_objects'] if n['name']==self.label)))
        with self.assertRaises(Exception):v.bind(i,self.text)

    def test_target_cannot_use_collapsed_alias(self):
        i=copy.deepcopy(self.instance);i['signals'].append(dict(name=self.label,left=14,right=14))
        with self.assertRaises(Exception):v.bind(i,self.text)

    def test_actual_host_full_five_phase(self):
        env=v.context()
        c=dict(self.config)
        result=env['host_hook'](c,env['selection'](c),v.old.candidate(c['instances']))
        self.assertEqual(result['scope_inventories'],90)
        self.assertEqual(result['per_object_GUI_select_calls'],0)
        self.assertFalse(result['EDA_started'])

    def test_fresh_prepare_check_context(self):
        with tempfile.TemporaryDirectory(dir=v.old.life.OUT,prefix='soc61-v2-host-test-') as tmp:
            out=Path(tmp)/'prepared'
            # Production requires a direct OUT child; use the fresh temporary
            # directory itself after removing its empty initial directory.
            out=Path(tmp);out.rmdir()
            try:
                v.prepare(out)
                seal=v.old.life.digest(out/'config.json')
                c=v.check(out,seal)
                self.assertEqual(c['schema'],'SOC_CONSTANTS61_LOCAL_NATIVE_PREPARED_V2')
                self.assertIn(str(Path(v.__file__).resolve()),c['pins'])
                self.assertIn(str(Path(__file__).resolve()),c['pins'])
                self.assertIn(str(v.old.TCL),c['pins'])
                self.assertIn(str(Path(v.__file__).resolve()),(out/'selection.tcl').read_text())
                with self.assertRaises(Exception):v.verify(out,seal)
                with self.assertRaises(Exception):v.run(out,seal,'not-parent-reviewed')
            finally:
                import shutil
                shutil.rmtree(out,ignore_errors=True)


if __name__=='__main__':unittest.main()
